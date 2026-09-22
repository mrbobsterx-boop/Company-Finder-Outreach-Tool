"""Renders Jinja2 mail templates, always injecting an unsubscribe link.

The unsubscribe URL is built here (not left to the template author) so
every outgoing email carries it regardless of what a template does or
doesn't reference explicitly.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader, select_autoescape


def build_unsubscribe_url(base_url: str, email: str) -> str:
    return f"{base_url.rstrip('/')}?{urlencode({'email': email})}"


def render_template(templates_dir: str | Path, template_name: str, context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(template_name)
    return template.render(**context)
