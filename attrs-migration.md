# Attrs Migration

This document covers what you need to know about migrating from [pydantic V1](https://pydantic.dev/docs/validation/1.10/overview/) to [attrs](https://www.attrs.org/en/stable/) and some hints about working productively with attrs going forward.

## Justification

Attrs is a much simpler way to do validation for `echo` without all the funny business/magic that pydantic introduces.

- There is no copying of objects behind your back when you mutate an object.
- Attrs uses a decorator on the class and creates the initialiser (`__init__`) for you. It also adds `__repr__` and `__eq__` for you. It gives you a few hooks for e.g. `__attrs_post_init__` that allow you to customize the process if required.
- There is no messing with class hierarchy. Attrs doesn't use inheritance for this reason. It uses a decorator instead. That means the only inheritance in your classes is the one you put there.

## How to migrate from Pydantic to Attrs

The following list is a brief description of how `echo` was migrated from pydantic to attrs. This is only meant to illustrative. Reading the echo code and seeing the changes made is the best way to understand migration.

- Remove all inheritance from pydantics `BaseModel`. Use attrs `@define` decorator on each class instead.
- Replace `Field` with `field` (attrs field helper)
  - If using factories for default values, replace `default_factory` with `factory`.
- Make sure all attributes have type annotations (See [Gotcha 1](#attrs-gotchas)).
- Replace attribute default values with one of the following ways of doing defaults in attrs:
  - directly on the instance variable `a: int = 1` (this is the same as pydantic)
  - using the field helper with a default `a: int = field(default=1)`
  - using the field helper with a factory `a: int = field(factory=list)`
  - using a separate declaration `@a.default...`. Example: `@port_name.default` on `Port` class. These can be particularly useful when the attributes default value depends on other attributes.
- Replace pydantic validating type annotations (PositiveInt, NonNegativeFloat etc.) with attrs built-in validators.
  - For example `a: NonNegativeFloat` becomes `a: int = field(..., validator=validators.ge(0))`. This is one of the most common changes made in `echo`. The following table shows the relationship between pydantic type annotations (that trigger validation) and attrs equivalent validators:

| pydantic type annotation | attrs equivalent validator |
| --- | --- |
| `PositiveFloat` | `validators.gt(0)` |
| `NegativeFloat` | `validators.lt(0)` |
| `NonPositiveFloat` | `validators.le(0)` |
| `NonNegativeFloat` | `validators.ge(0)` |
| `PositiveFloat|None` | `validators.optional(validators.gt(0))` |
| `NegativeFloat|None` | `validators.optional(validators.lt(0))` |
| `NonPositiveFloat|None` | `validators.optional(validators.le(0))` |
| `NonNegativeFloat|None` | `validators.optional(validators.ge(0))` |

- Replace pydantic `@validator`s
  - use the field helper `b: int = field(..., validator=my_custom_validator)` or decorator `@a.validator...`. Example: `@time_periods.validator` on `Window` class.
- ~~Replace root validators with calls the validator in `__attrs_post_init__`.~~ This will only validate on instance creation and not each time the attribute is set. See below for a better approach.
- Replace root validators with validators on each of the attributes involved in the relationship. Example: `reset_periods_validator` and `import_or_export_demand_set_validator` on `DemandCharge` class.

In addition to the above changes, it was also necessary to replace all references to pydantic's `ValidationError` with python's `ValueError` across the unit tests.

## Attrs Gotchas

Pydantic does a lot of magic behind the scenes to make your life "easier". Attrs is much simpler but this means you are often required to do a few things manually or be a bit more thoughtful/careful when using it. Here a few attrs gotchas to be aware of.

### Gotcha 1: Forgetting to add type annotations to attributes

Always use type annotations on *all* attributes. Don't forgot to use type annotations on attributes that a defined with attr's `field` specifier.

The short explanation is that type annotations indicate to attrs that an attribute is an instance variable (rather than a class variable). This might seem strange at first but is in fact how [dataclasses](https://docs.python.org/3/library/dataclasses.html) work.

### Gotcha 2: Forgetting to add type annotations when overriding attributes in subclasses

Any time we want to change the behaviour of an attribute in a subclass (whether that is setting a new default as above, or adding a validator etc.) we need to remember all the full attribute definition.

The reasons for this is the same reason as gotcha 1.

Let's say we want to override the default value of attribute `b` in a subclass,

```python
@define
class ParentClass():
    b: int = 2

@define
class ChildClass(ParentClass):
    b = 999
```

In attrs this code won't work how you expect. In fact the `b = 999` which have no effect at all!

Instead we need the full attribute definition in the subclass (i.e. with the type annotation),

```python
@define
class ParentClass():
    b: int = 2

@define
class ChildClass(ParentClass):
    b: int = 999
```

### Gotcha 3: Forgetting to add `@define` to subclasses

In general you always want to decorate subclasses with `@define`.

This is a must if the subclass adds new attributes or overrides the behaviour of attributes (See gotchas 1 and 2).

In the following example, `b` will have a default value of 2 even with instances of `ChildClass`.

```python
@define
class ParentClass():
    b: int = 2

# ChildClass missing @define
class ChildClass(ParentClass):
    b: int = 999
``` 

Technically this doesn't seem to be necessary on subclasses that only add new methods or override methods. In this case it's still preferable to used `@define`. Some else could subclass your class and without the decorator any attributes they define would get ignored.

### Gotcha 4: Error messages about attribute ordering/default values

When working with attrs it is common is see the following warning message in your IDE:

> Fields without default values cannot appear after fields with default values

To understand what happening let's look at an example,

```python
@define
class Parent:
    a: int
    b: bool = True 

@define
class Child(Parent):
    c: str
```

Here we have a two classes with a `Child` inheriting from `Parent`. Let's recreate the `__init__` method for `Child` that attrs will make for us,

```python
def __init__(a: int, b: bool = True, c: str):
    ...
```

Here `a`, `b` and `c`  are all positional arguments.

Now we can see the problem. Argument `c` comes after `b` which has a default value. Positional arguments are not allowed to come after arguments with defaults in python.

There are two ways to fix this:

1. Supply a default value for the attribute or,
2. Make the attribute keyword only.

Applying these solutions to our example gives us:

```python
@define
class Child(Parent):
    c: str = "default-value"
    # c: str | None = None  # this is another approach
```

or,

```python
@define
class Child(Parent):
    c: str = field(kw_only=True)
```

### Gotcha 5: Extra attributes

Pydantic allows extra attributes to be attached to instances when the appropriate configuration is used,

```py
class BaseModel(PydanticBaseModel):
    """Create a modified base model with the config we want."""

    class Config:
        validate_assignment = True
        extra = "ignore"  # <- this attribute allows extra attributes on any model
        arbitrary_types_allowed = True
```

Here `extra` configuration option allows this behaviour.

attrs doesn't have an equivalent and is more pythonic: if you want attributes, then you need to specify explictly on a class.
