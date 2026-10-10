# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
from django.conf import settings

settings.configure()


project = "rest-filters"
copyright = "2026, şuayip üzülmez"
author = "şuayip üzülmez"
release = "0.8.0-beta"

# -- General configuration ---------------------------------------------------
extensions = [
    "sphinx.ext.autodoc",
]

templates_path = ["_templates"]
exclude_patterns = []

autoclass_content = "class"
autodoc_class_signature = "separated"

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]
html_css_files = [
    "https://fonts.googleapis.com/css2?family=Geist:wght@100..900"
    "&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&display=swap",
    "fonts.css",
]

pygments_style = "default"
pygments_dark_style = "github-dark"
