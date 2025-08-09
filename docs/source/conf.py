# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
from django.conf import settings

settings.configure()


project = "rest-filters"
copyright = "2025, şuayip üzülmez"
author = "şuayip üzülmez"
release = "0.4.3"

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
]

templates_path = ["_templates"]
exclude_patterns = []

autoclass_content = "both"

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]

pygments_style = "default"
pygments_dark_style = "github-dark"
