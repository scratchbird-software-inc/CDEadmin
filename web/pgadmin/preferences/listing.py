##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Group preferences into the module/category tree File > Preferences shows."""

from flask_babel import gettext


def _group_pref_by_categories(pref, res, label):
    """
    Group preference by categories type.
    :param pref: preference data.
    :param res: response for request.
    :param label: get label.
    :return:
    """
    for pref_d in pref:
        if len(pref_d['categories']):
            _iterate_categories(pref_d, label, res)


def _iterate_categories(pref_d, label, res):
    """
    Iterate preference categories.
    :param pref_d: preference data
    :param label: get label.
    :param res: response.
    :return:
    """
    om = {
        "id": pref_d['id'],
        "label": gettext(pref_d['label']),
        "inode": True,
        "open": True,
        "children": [],
        "value": gettext(pref_d['label']),
        "name": pref_d['name']
    }

    for c in pref_d['categories']:
        # Hidden preferences have their own editors (for example connector
        # visibility, or View > Appearance and accessibility); they stay in
        # get_all for the client store but are not listed in this dialog.
        visible = [p for p in c['preferences'] if not p.get('hidden')]
        if not visible:
            continue
        for p in visible:
            if 'label' in p and p['label'] is not None:
                p['label'] = gettext(p['label'])
            if 'help_str' in p and p['help_str'] is not None:
                p['help_str'] = gettext(p['help_str'])
        c = {**c, 'preferences': visible}
        oc = {
            "id": c['id'],
            "mid": pref_d['id'],
            "name": c['name'],
            "label": gettext(c['label']),
            "value": '{0}{1}'.format(c['id'], gettext(c['label'])),
            "inode": False,
            "open": False,
            "preferences": sorted(c['preferences'], key=label),
            "showCheckbox": False
        }

        (om['children']).append(oc)
    om['children'] = sorted(om['children'], key=label)

    if om['children']:
        res.append(om)
