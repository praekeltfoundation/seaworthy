{{ fullname | escape | underline}}

.. automodule:: {{ fullname }}
   :members:
{%- if '__apigen_undoc_members__' in members %}
   :undoc-members:
{%- endif -%}
{%- if '__apigen_inherited_members__' in members %}
   :inherited-members:
{%- endif -%}
{# These comments are a hack... #}
{# ...to give us a trailing newline. #}
