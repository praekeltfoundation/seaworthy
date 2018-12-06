# As of pytest 4, conftest files with pytest_plugins must be at the package
# top-level. This plugin is only used for the tests under tests-pytest, though.
pytest_plugins = ['pytester']
