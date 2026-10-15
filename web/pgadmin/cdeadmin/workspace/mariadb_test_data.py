"""MariaDB-specific admission over the shared bounded recipe mechanics."""
from . import mysql_test_data as recipes

FORMAT = 'scratchrobin.mariadb.test-data@1'


def template(model):
    return recipes.template(model, engine='mariadb')


def generate(model, recipe):
    return recipes.generate(model, recipe, engine='mariadb')
