"""
Demo: Delta queries vs per-notification GETs.

Simulates a mailbox, push notifications, missed notifications,
coalescing, and how delta queries reconcile changes since a token.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import random


@dataclass
class Message:
    id: str
    subject: str
    deleted: bool = False


@dataclass
class Mailbox:
    """Simulated mailbox with change log and delta tokens."""
    messages: Dict[str, Message] = field(default_factory=dict)
    change_log: List[Tuple[int, str, Optional[Message]]] = field(default_factory=list)
    _version: int = 0

    def _record_change(self, change_type: str, message: Optional[Message]) -> None:
        self._version += 1
        self.change_log.append((self._version, change_type, message))

    def add_message(self, message: Message) -> None:
        self.messages[message.id] = message
        self._record_change("created", message)

    def update_message(self, message_id: str, subject: str) -> None:
        msg = self.messages[message_id]
        msg.subject = subject
        self._record_change("updated", msg)

    def delete_message(self, message_id: str) -> None:
        msg = self.messages[message_id]
        msg.deleted = True
        self._record_change("deleted", msg)

    def get_message(self, message_id: str) -> Optional[Message]:
        return self.messages.get(message_id)

    def delta(self, since_token: Optional[int]) -> Tuple[List[Tuple[str, Message]], int]:
        start_version = since_token or 0
        changes: List[Tuple[str, Message]] = []
        for version, change_type, message in self.change_log:
            if version > start_version and message is not None:
                changes.append((change_type, message))
        return changes, self._version


@dataclass
class Notification:
    """Simulated push notification (may include message id but is unreliable)."""
    message_id: str


def simulate_push_notifications(mailbox: Mailbox, event_ids: List[str], drop_rate: float) -> List[Notification]:
    notifications: List[Notification] = []
    for message_id in event_ids:
        if random.random() > drop_rate:
            notifications.append(Notification(message_id=message_id))
    return notifications


def demo():
    random.seed(7)

    mailbox = Mailbox()

    # Initial messages
    mailbox.add_message(Message(id="m1", subject="Welcome"))
    mailbox.add_message(Message(id="m2", subject="Policy Update"))

    # Simulated change events
    # Add m3, update m2, delete m1, add m4
    mailbox.add_message(Message(id="m3", subject="New Quote"))
    mailbox.update_message("m2", "Policy Update (Revised)")
    mailbox.delete_message("m1")
    mailbox.add_message(Message(id="m4", subject="Claim Notice"))

    # Push notifications (some are dropped)
    # Assume each change triggered a notification containing a message id
    event_ids = ["m3", "m2", "m1", "m4"]
    notifications = simulate_push_notifications(mailbox, event_ids, drop_rate=0.5)

    print("=== Scenario: Push -> GET per notification ===")
    processed_get = []
    for note in notifications:
        msg = mailbox.get_message(note.message_id)
        if msg is None:
            continue
        # GET-style processing only sees message tied to notification
        processed_get.append((note.message_id, msg.subject, msg.deleted))

    print("Notifications received:", [n.message_id for n in notifications])
    print("Processed via GET:", processed_get)

    print("\n=== Scenario: Push -> Delta reconcile ===")
    # Start from a previous token (no prior changes processed)
    delta_token = None
    # One push wakes the worker; delta pulls everything since last token
    changes, delta_token = mailbox.delta(delta_token)
    processed_delta = [(m.id, m.subject, m.deleted, change) for change, m in changes]

    print("Delta changes:")
    for item in processed_delta:
        print("  ", item)
    print("New delta token:", delta_token)

    print("\n=== Summary ===")
    print("GET processing missed changes if notifications were dropped.")
    print("Delta processing reconciled all changes since the last token.")


if __name__ == "__main__":
    demo()
