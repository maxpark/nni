# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from __future__ import annotations

__all__ = [
    'uid', 'reset_uid',
    'NoContextError', 'ContextStack', 'get_current_context',
    'label_scope', 'auto_label',
]

import logging
from collections import defaultdict
from typing import Any, List, cast

_last_uid = defaultdict(int)

_logger = logging.getLogger(__name__)


def uid(namespace: str = 'default') -> int:
    """Global counter for unique id. Not thread-safe."""
    _last_uid[namespace] += 1
    return _last_uid[namespace]


def reset_uid(namespace: str = 'default') -> None:
    """Reset counter for a specific namespace."""
    _last_uid[namespace] = 0


class NoContextError(Exception):
    """Exception raised when context is missing."""
    pass


class ContextStack:
    """
    This is to maintain a globally-accessible context environment that is visible to everywhere.

    To initiate::

        with ContextStack(namespace, value):
            ...

    Inside the context, you can access the nearest value put into ``with``::

        get_current_context(namespace)

    Notes
    -----
    :class:`ContextStack` is not multi-processing safe. Also, the values will get cleared for a new process.
    """

    _stack: dict[str, list] = defaultdict(list)

    def __init__(self, key: str, value: Any):
        self.key = key
        self.value = value

    def __enter__(self):
        self.push(self.key, self.value)
        return self

    def __exit__(self, *args, **kwargs):
        self.pop(self.key)

    @classmethod
    def push(cls, key: str, value: Any):
        cls._stack[key].append(value)

    @classmethod
    def pop(cls, key: str) -> Any:
        if not cls._stack[key]:
            raise NoContextError(f'Context with key {key} is empty.')
        return cls._stack[key].pop()

    @classmethod
    def top(cls, key: str) -> Any:
        if not cls._stack[key]:
            raise NoContextError(f'Context with key {key} is empty.')
        return cls._stack[key][-1]

    @classmethod
    def stack(cls, key: str) -> list:
        return list(cls._stack[key])


def get_current_context(key: str) -> Any:
    return ContextStack.top(key)


_LABEL_NAMESPACE_CONTEXT_KEY = 'label_namespace'


class label_scope:
    """
    To support automatic labeling of mutables.

    Labels are named like a file-system. The analogy here is that:
    scope is like a directory, and label is like a file.
    The label name is like a file name. It can't contain slash (``/``) or underscore (``_``).
    The scope name is like a directory name. It also can't contain ``/`` or ``_``.
    When we refer to a "label", we will usually use the full name, which is like an absolute file path.

    :class:`label_scope` is usually jointly used with :func:`auto_label`,
    where :class:`label_scope` is used to generate the "scope" (directory) part,
    and :func:`auto_label` is used to generate the "name" (file) part.
    A :class:`label_scope` can be entered, and then :func:`auto_label` can be called inside.
    The labels as well as scopes generated inside can be automatically named with natural integers starting from 1
    (see examples below), and we guarantee the generation of labels to be reproducible.
    It can also be naturally nested.

    :class:`label_scope` is NOT thread-safe. The behavior is undefined if multiple threads are
    trying to enter the scope at the same time.

    :class:`label_scope` is implemented based on :class:`ContextStack`.

    Parameters
    ----------
    basename
        The last part of current scope name. If not specified, it will be generated by the parent scope.
        If the parent scope is not found, the scope name will be ``param`` by default.
        :class:`label_scope` is idempotent, so ``basename`` also accepts :class:`label_scope` and :class:`label`,
        though it will return a new instance.

    Examples
    --------
    >>> with label_scope('model'):
    ...     label1 = auto_label()       # model/1
    ...     label2 = auto_label()       # model/2
    ...     label3 = auto_label('foo')  # model/foo
    ...     with label_scope():
    ...         label4 = auto_label()   # model/3/1
    ...         label5 = auto_label()   # model/3/2
    ...     with label_scope('another'):
    ...         label6 = auto_label()   # model/another/1
    ...     with label_scope('model'):
    ...         label7 = auto_label()   # model/model/1
    >>> with label_scope('model'):
    ...     label8 = auto_label()       # model/1, because the counter is reset
    >>> with label_scope():
    ...     label9 = auto_label()       # global/1/1
    """

    def __init__(self, basename: str | label | label_scope | None = None, *, _path: list[str] | None = None):
        if isinstance(basename, label):
            _path = basename.parts
            basename = None

        if isinstance(basename, label_scope):
            _path = basename.path
            basename = None

        if basename is not None:
            _validate_label_name(basename)

        # basename is not assigned at this point.
        # It will be assigned later when "with" is entered.
        self.basename = basename

        # NOTE: Internal usages only.
        # The full "path" of current scope.
        # It should also contain the part after the last ``/``.
        # No validation here, because it's not considered as public API.
        self.path = _path
        if self.path is not None:
            assert self.path, 'path should not be empty'

        if _path:
            self.basename = _path[-1]

        # The indicator flag to indicate whether the scope is entered.
        self.activated = False

    def __enter__(self):
        # When path is set, it means the scope has been entered before.
        # Its path should not change.
        # Otherwise, we compute the path based on its parent.

        if self.path is None:
            parent_scope = label_scope.current()
            if self.basename is None:
                if parent_scope is None:
                    # NOTE: It's not recommended to use the default namespace because the stable label numbering cannot be guaranteed.
                    # However, we allow such usage currently because it's mostly used in evaluator,
                    # whose initialization relies on trace, and doesn't need to be reproducible in trial code.
                    _logger.warning(
                        'Label is not provided, and label scope is also missing. Global numbering will be used. '
                        'Note that we always recommend specifying `label=...` manually.',
                    )
                    # No parent and doesn't have a name, put it under global namespace.
                    parent_scope = label_scope.global_()
                self.basename = parent_scope.next_label()

            if parent_scope is not None:
                self.path = parent_scope.path + [self.basename]
            else:
                self.path = [self.basename]

        # Since path is sometimes already set (e.g., when re-enter),
        # parent_scope is not necessarily the real parent of current scope.
        # We actually allow this and only look at the current scope below.

        # Enter the label namespace resets the counter associated with the namespace.
        # It also pushes itself into the stack, so as to support nested namespace.
        # For example, currently the top of stack is ['foo', 'bar'], and ['foo', 'bar', '3'] is used,
        # the next thing up is ['foo', 'bar', '4'].
        # `reset_uid` to count from zero for "foo/bar/4"
        ContextStack.push(_LABEL_NAMESPACE_CONTEXT_KEY, self)
        reset_uid(self.absolute_scope)
        self.activated = True
        return self

    def __exit__(self, *args, **kwargs):
        ContextStack.pop(_LABEL_NAMESPACE_CONTEXT_KEY)
        self.activated = False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, label_scope):
            return False
        return self.path == other.path

    @property
    def absolute_scope(self) -> str:
        """Alias of name."""
        return self.name

    @property
    def name(self) -> str:
        """The full name of current namespace.

        For example, ``model/cell/2``.
        """
        self.check_entered()
        assert self.path is not None, 'This should never happen.'
        return cast(str, label(self.path))

    def __repr__(self):
        return f'label_scope({self.absolute_scope!r})'

    def next_label(self) -> str:
        """Generate the "name" part."""
        return str(uid(self.absolute_scope))

    def check_entered(self) -> None:
        """Raise error if the scope is not entered."""
        if self.path is None:
            raise ValueError(f'label_scope "{self.basename}" is not entered yet.')

    @staticmethod
    def current() -> label_scope | None:
        """Fetch the nearest label scope activated by ``with``.

        If label scope is never used, or we are currently within no with-block,
        return none.

        Examples
        --------
        >>> with label_scope() as scope1:
        ...     # somewhere in the middle of the code.
        ...     label_scope.current()     # Return scope1
        """
        try:
            return ContextStack.top(_LABEL_NAMESPACE_CONTEXT_KEY)
        except NoContextError:
            return None

    @staticmethod
    def global_() -> label_scope:
        """Fetch the global label scope.

        This label scope can be created on-the-fly and can live without the with-blocks.
        """
        return label_scope('global', _path=['global'])


class label(str):
    """A :class:`label` should work like a :class:`str`,
    but it also records extra information to help reusing the label.

    As :func:`auto_label` prepends a prefix to the label,
    we need to identify whether the label has been processed by :func:`auto_label` or not,
    which is done by :class:`label`.

    Generally, it should work like a string which contains the label name.
    """

    parts: list[str]

    def __new__(cls, parts: list[str] | str):
        if isinstance(parts, str):
            obj = super().__new__(cls, parts)
            obj.parts = [parts]
        else:
            obj = super().__new__(cls, '/'.join(parts))
            obj.parts = parts

        return cast(label, obj)

    def as_scope(self) -> label_scope:
        """Convert the label to a label scope."""
        return label_scope(_path=self.parts)


def auto_label(name: str | label | None = None, scope: label_scope | None = None) -> str:
    """Automatically generate a formatted and reproducible label.

    In case ``name`` is not set, the label name will use the uid sequence of ``scope``.
    If ``scope`` is not set, it will fetch the nearest scope.
    If no scope is found, it will use the global scope (:meth:`label_scope.global_`).

    If the scope is found and is not global scope, the scope's full name will be prepended to the label,
    i.e., the label will then be formatted as ``{scope}/{label}``.
    Otherwise, there are two cases. Firstly, if label is manually specified, it will be returned directly.
    Secondly, we rely on the global scope to generate the label name, and the scope name will still be prepended.
    The rules can be better explained with the examples below.

    Notes
    -----
    We always recommend specifying the label manually.

    Parameters
    ----------
    name
        The label name to use. If not specified, it will be generated by the scope.
    scope
        The scope to use. If not specified, the nearest scope will be used.

    Returns
    -------
    A string that represents the label.
    For advanced users, please be advised that
    the returned object would be a :class:`label` object, rather than a string.
    This is to make sure :func:`auto_label` is idempotent.
    We expect some side effects, but it should work seamlessly with most of the code.

    Examples
    --------
    >>> label1 = auto_label('bar')          # bar, because the scope is global
    >>> label2 = auto_label()               # global/1, because label is not provided
    >>> with label_scope('foo'):
    ...     label3 = auto_label()           # foo/1, because in the scope "foo"
    >>> with label_scope():                 # scope is global/2
    ...     label4 = auto_label()           # global/2/1
    >>> with label_scope('another'):
    ...     label5 = auto_label()           # another/1
    ...     label6 = auto_label('thing')    # another/thing
    ...     label7 = auto_label()           # another/2
    """

    if isinstance(name, label):
        # Already a label, no need to do anything.
        return cast(str, name)

    # Has scope is a special case, because it might not have been entered.
    if scope is not None:
        if not isinstance(scope, label_scope):
            raise TypeError('scope must be an instance of label_scope')
        if name is None:
            name = scope.next_label()
        scope.check_entered()
        return cast(str, label([*cast(List[str], scope.path), name]))

    # Fake a label scope and return its name directly.
    with label_scope(name) as scope:
        assert scope.path is not None
        return cast(str, label(scope.path))


def _validate_label_name(name: str) -> None:
    if not isinstance(name, str):
        raise TypeError('label must be a string')
    if not name:
        raise ValueError('label cannot be empty')
    if '/' in name:
        raise ValueError('label cannot contain slash (`/`). Please use `label_scope` to build hierarchical labels.')
