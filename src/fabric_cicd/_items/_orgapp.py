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

    In the source-controlled definition.json, referenced items are identified by their
    workspace-agnostic logical id via the "itemLogicalId" key. The Fabric API expects the
    deployed item id ("itemId") and the object id of the folder the item resides in
    ("folderObjectId", which is the workspace id when the item is not inside a folder).
    This function replaces each "itemLogicalId" reference with the resolved "itemId" and
    "folderObjectId" of the respective deployed item.

    Args:
        workspace_obj: The FabricWorkspace object.
        _item_obj: The item object (unused).
        file_obj: The file object.
    """
    if file_obj.name != ORG_APP_DEFINITION_FILE:
        return file_obj.contents

    definition_body = json.loads(file_obj.contents)
    processed_body = _replace_item_references(workspace_obj, definition_body)

    return json.dumps(processed_body, indent=2)


def _replace_item_references(workspace_obj: FabricWorkspace, node: object) -> object:
    """
    Recursively walks the definition body and replaces "itemLogicalId" references with the
    resolved "itemId" and "folderObjectId" of the respective deployed item.

    Args:
        workspace_obj: The FabricWorkspace object.
        node: The current node (dict, list, or scalar) in the definition body.
    """
    if isinstance(node, dict):
        if "itemLogicalId" in node:
            node = _resolve_reference(workspace_obj, node)
        return {key: _replace_item_references(workspace_obj, value) for key, value in node.items()}
    if isinstance(node, list):
        return [_replace_item_references(workspace_obj, element) for element in node]
    return node


def _resolve_reference(workspace_obj: FabricWorkspace, node: dict) -> dict:
    """
    Resolves a single item reference by replacing its "itemLogicalId" with the deployed
    "itemId" and "folderObjectId" while preserving the original key order.

    Args:
        workspace_obj: The FabricWorkspace object.
        node: The reference object containing an "itemLogicalId" key.
    """
    item_type = node.get("itemType")
    logical_id = node.get("itemLogicalId")

    referenced_name = (
        workspace_obj._convert_id_to_name(item_type, logical_id, "Repository")
        if item_type in workspace_obj.repository_items
        else None
    )
    if referenced_name is None:
        msg = f"Cannot resolve item reference with logicalId '{logical_id}' of type '{item_type}' in the repository."
        raise ParsingError(msg, logger)

    item_details = workspace_obj.repository_items[item_type][referenced_name]
    if not item_details.guid:
        msg = (
            f"Cannot replace logicalId '{logical_id}' as referenced item "
            f"'{referenced_name}.{item_type}' is not yet deployed."
        )
        raise ParsingError(msg, logger)

    # folderObjectId is the object id of the folder the item lives in, or the workspace id
    # when the item is not inside a folder
    folder_object_id = item_details.folder_id or workspace_obj.workspace_id

    resolved_node = {}
    for key, value in node.items():
        if key == "itemLogicalId":
            resolved_node["itemId"] = item_details.guid
            resolved_node["folderObjectId"] = folder_object_id
        else:
            resolved_node[key] = value

    return resolved_node


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
