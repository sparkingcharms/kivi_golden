# Shortcuts

Shortcuts are the fourth memory kind in the Golden implementation. A shortcut is a phrase the user invents and explicitly defines, such as `professorize this`.

The important boundary is **interpretation is not permission**. Teaching a phrase first produces a readable draft of what Kivi understood. It is not stored until the user confirms it.

Once saved, a shortcut carries the same memory metadata as the existing system: provenance, status, scope and usage history. It can be limited to an app and to a surface such as a selection.

Shortcut matching is deliberately conservative. Character-level trigger similarity catches phrases that sound alike, while a trigger floor prevents ordinary requests such as `make this shorter` from accidentally firing an unrelated shortcut. When two shortcuts are close enough, Kivi asks instead of guessing and records the collision.

A matched shortcut produces a proposed rewrite. It never sends, posts or changes the target application by itself. The user still presses Apply.

This keeps the shortcut feature inside the existing memory architecture rather than creating a separate personalization subsystem.
