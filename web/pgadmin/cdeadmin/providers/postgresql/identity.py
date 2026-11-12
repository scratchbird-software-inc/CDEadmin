"""The PostgreSQL provider's identity, importable without the provider.

The endpoint service decides whether a server is the preserved PostgreSQL
provider by these four values alone; reading them from the provider module
would import its drivers and templates (and, through them, the application
model) for a comparison of strings.
"""
PROVIDER_ID = 'org.pgadmin.postgresql'
PROVIDER_VERSION = '9.17.0'
PROFILE_ID = 'postgresql-native'
PROFILE_VERSION = '18.3'
