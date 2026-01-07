from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get item from dictionary by key
    Usage: {{ dict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key, [])


@register.filter
def replace(value, arg):
    """
    Template filter to replace substrings
    Usage: {{ value|replace:"old:new" }}
    """
    if not arg or ':' not in arg:
        return value
    old, new = arg.split(':', 1)
    return str(value).replace(old, new)
