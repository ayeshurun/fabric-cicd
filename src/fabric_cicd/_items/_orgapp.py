# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Functions to process and deploy Org App item."""

import json
import logging

from fabric_cicd import FabricWorkspace
from fabric_cicd._common._exceptions import ParsingError
from fabric_cicd._common._file import File
from fabric_cicd._common._item import Item
from fabric_cicd._items._base_publisher import ItemPublisher
from fabric_cicd.constants import EXCLUDE_PATH_REGEX_MAPPING, ItemType

logger = logging.getLogger(__name__)

# File within an Org App / Org App Audience item that holds references to other items
ORG_APP_DEFINITION_FILE = "definition.json"


def func_process_file(workspace_obj: FabricWorkspace, _item_obj: Item, file_obj: File) -> str:
    """
    Custom file processing for Org App and Org App Audience items.

    In the source-controlled definition.json, other items are referenced by their
    display name and type. To deploy the item, each reference must carry the deployed
    item id ("itemId") and the object id of the folder the item resides in
    ("folderObjectId", which is the workspace id when the item is not inside a folder).
    This function resolves every item reference and sets its "itemId" and
    "folderObjectId", regardless of whether the source reference used the
    workspace-agnostic "itemLogicalId" key.

    Args:
        workspace_obj: The FabricWorkspace object.
        _item_obj: The item object (unused).
        file_obj: The file object.
    """
    if file_obj.name != ORG_APP_DEFINITION_FILE:
        return file_obj.contents

    definition_body = json.loads(file_obj.contents)
    processed_body = _resolve_item_references(workspace_obj, definition_body)

    return json.dumps(processed_body, indent=2)


def _resolve_item_references(workspace_obj: FabricWorkspace, value: object) -> object:
    """
    Recursively walks the definition body and resolves every item reference to its
    deployed "itemId" and "folderObjectId".

    Args:
        workspace_obj: The FabricWorkspace object.
        value: The current value (dict, list, or scalar) in the definition body.
    """
    if isinstance(value, dict):
        if _is_item_reference(value):
            value = _resolve_reference(workspace_obj, value)
        return {key: _resolve_item_references(workspace_obj, child) for key, child in value.items()}
    if isinstance(value, list):
        return [_resolve_item_references(workspace_obj, element) for element in value]
    return value


def _is_item_reference(value: dict) -> bool:
    """
    Returns True when the value is a reference to another item, identified by an
    "elementType" of "item".

    Args:
        value: The value to inspect.
    """
    return value.get("elementType", "") == "item"


def _resolve_reference(workspace_obj: FabricWorkspace, reference: dict) -> dict:
    """
    Resolves a single item reference to the deployed item's "itemId" and "folderObjectId".

    The referenced item is located by its display name and type. The resolved ids are set
    regardless of whether the source reference used the "itemLogicalId" key.

    Args:
        workspace_obj: The FabricWorkspace object.
        reference: The reference object identifying another item.
    """
    item_type = reference.get("itemType", "")
    display_name = reference.get("displayName", "")

    item_details = workspace_obj.repository_items.get(item_type, {}).get(display_name)
    if item_details is None:
        msg = f"Cannot resolve referenced item '{display_name}' of type '{item_type}' in the repository."
        raise ParsingError(msg, logger)

    if not item_details.guid:
        msg = f"Cannot deploy reference to '{display_name}.{item_type}' as it is not yet deployed."
        raise ParsingError(msg, logger)

    # folderObjectId is the object id of the folder the item lives in, or the workspace id
    # when the item is not inside a folder
    folder_object_id = item_details.folder_id or workspace_obj.workspace_id

    return _apply_resolved_ids(reference, item_details.guid, folder_object_id)


def _apply_resolved_ids(reference: dict, item_id: str, folder_object_id: str) -> dict:
    """
    Returns a copy of the reference with "itemId" and "folderObjectId" set to the resolved
    values, dropping the workspace-agnostic "itemLogicalId" key when present while otherwise
    preserving the original key order.

    Args:
        reference: The reference object identifying another item.
        item_id: The resolved deployed item id.
        folder_object_id: The resolved folder object id (or workspace id).
    """
    resolved = {}
    item_id_set = False
    folder_set = False

    for key, value in reference.items():
        # Replace the logical id reference with both resolved ids, grouped in place
        if key == "itemLogicalId":
            if not item_id_set:
                resolved["itemId"] = item_id
                item_id_set = True
            if not folder_set:
                resolved["folderObjectId"] = folder_object_id
                folder_set = True
        # Overwrite an existing id in place
        elif key == "itemId":
            if not item_id_set:
                resolved["itemId"] = item_id
                item_id_set = True
        elif key == "folderObjectId":
            if not folder_set:
                resolved["folderObjectId"] = folder_object_id
                folder_set = True
        else:
            resolved[key] = value

    if not item_id_set:
        resolved["itemId"] = item_id
    if not folder_set:
        resolved["folderObjectId"] = folder_object_id

    return resolved


class OrgAppPublisher(ItemPublisher):
    """Publisher for Org App items."""

    item_type = ItemType.ORG_APP.value

    def publish_one(self, item_name: str, _item: Item) -> None:
        """Publish a single Org App item."""
        self.fabric_workspace_obj._publish_item(
            item_name=item_name,
            item_type=self.item_type,
            exclude_path=EXCLUDE_PATH_REGEX_MAPPING.get(self.item_type),
            func_process_file=func_process_file,
        )
