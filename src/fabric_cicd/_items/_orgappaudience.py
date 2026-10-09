# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Org App Audience item."""

from fabric_cicd._common._item import Item
from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd._items._orgapp import func_process_file
from fabric_cicd.constants import ItemType


class OrgAppAudiencePublisher(ItemPublisher):
    """Publisher for Org App Audience items."""

    item_type = ItemType.ORG_APP_AUDIENCE.value

    def publish_one(self, item_name: str, _item: Item) -> None:
        """Publish a single Org App Audience item."""
        self.fabric_workspace_obj._publish_item(
            item_name=item_name, item_type=self.item_type, func_process_file=func_process_file
        )
