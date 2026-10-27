# ScratchRobin admission and cutover gates for the pinned upstream utility.
package pt_online_schema_change_plugin;
use strict;
use warnings;
use JSON::PP;
use Time::HiRes qw(sleep);

sub new {
    my ($kind, %settings) = @_;
    open my $input, '<', 'binding.json' or die 'Missing reviewed source binding';
    local $/; my $binding = decode_json(<$input>); close $input;
    my $dbh = $settings{cxn}->dbh();
    my ($locked) = $dbh->selectrow_array('SELECT GET_LOCK(?,5)', undef, $binding->{advisory});
    die 'Controlled native utility lock unavailable' unless defined($locked) && $locked == 1;
    for my $connection ($settings{cxn},$settings{aux_cxn}) {
        $connection->dbh()->do('SET SESSION sql_mode=?',undef,$binding->{sql_mode});
    }
    return bless {settings => \%settings, binding => $binding}, $kind;
}
sub publish {
    my ($self, $stage, %facts) = @_;
    my $dbh = $self->{settings}->{cxn}->dbh();
    my ($uuid, $account, $database, $connection, $thread) = $dbh->selectrow_array(
        'SELECT @@server_uuid,CURRENT_USER(),DATABASE(),CONNECTION_ID(),PS_CURRENT_THREAD_ID()');
    die 'Native utility reached a different server or account' unless
        $uuid eq $self->{binding}->{server_uuid} && $account eq $self->{binding}->{account}
        && $database eq $self->{binding}->{database};
    my ($owner) = $dbh->selectrow_array('SELECT IS_USED_LOCK(?)',undef,$self->{binding}->{advisory});
    die 'Native utility lost its owned cooperating lock' unless defined($owner) && "$owner" eq "$connection";
    my %event = (stage => $stage, server_uuid => $uuid, account => $account,
        connection_id => "$connection", thread_id => defined($thread) ? "$thread" : undef, %facts);
    open my $output, '>', '.gate.pending' or die 'Cannot retain native stage';
    print $output encode_json(\%event); close $output;
    rename '.gate.pending', 'gate.json' or die 'Cannot publish native stage';
    return $dbh;
}
sub check_cancel {
    die 'ScratchRobin requested cancellation' if -e 'cancel';
    die 'ScratchRobin replica observer heartbeat expired' unless -e 'heartbeat' && time()-(stat('heartbeat'))[9] <= 10;
}
sub before_create_new_table {
    my ($self) = @_;
    my $dbh = $self->publish('before-create');
    my $target = $self->{binding}->{qualified_table};
    my @row = $dbh->selectrow_array('SHOW CREATE TABLE '.$target);
    $self->publish('before-create', native_definition => $row[1]);
    until (-e 'create.allowed') {check_cancel(); sleep(.1);}
}
sub after_create_new_table {
    my ($self,%args) = @_;
    my $table=$args{new_tbl};
    open my $output,'>','new-table.json' or die 'Cannot retain native copy identity';
    print $output encode_json({database=>$table->{db},table=>$table->{tbl}});close $output;
}
sub wait_for_lag {
    check_cancel();
    while (-e 'lag.pause') {check_cancel();sleep(.1);}
}
sub before_copy_rows {my ($self) = @_;$self->publish('copying');wait_for_lag();}
sub on_copy_rows_after_nibble {wait_for_lag();}
sub before_swap_tables {
    my ($self) = @_;$self->publish('cutover-waiting');
    until (-e 'cutover.allowed') {check_cancel();sleep(.1);}
    $self->publish('cutover-admitted');
}
sub after_swap_tables {
    my ($self,%args) = @_;
    my $table=$args{old_tbl};
    open my $output,'>','old-table.json' or die 'Cannot retain native prior-table identity';
    print $output encode_json({database=>$table->{db},table=>$table->{tbl}});close $output;
    open my $done,'>','swapped' or die 'Cannot retain native swap';close $done;$self->publish('native-swap-returned');
}
sub after_drop_old_table {my ($self) = @_;$self->publish('native-old-table-drop-returned');}
sub after_drop_triggers {my ($self) = @_;$self->publish('native-trigger-cleanup-returned');}
sub before_exit {my ($self) = @_;$self->publish('native-utility-exit');}
1;
