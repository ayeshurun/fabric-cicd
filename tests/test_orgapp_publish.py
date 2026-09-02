# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""
Tests for Org App / Org App Audience custom file processing.

The source-controlled definition.json references other items by their display name and type.
On deployment these references must carry the deployed "itemId" and the "folderObjectId" of
the folder the referenced item resides in (the workspace id when the item is not inside a
folder). These ids are resolved regardless of whether the source reference used the
workspace-agnostic "itemLogicalId" key.
"""

import json

import pytest

from fabric_cicd._common._exceptions import ParsingError
from fabric_cicd._common._item import Item
from fabric_cicd._items._orgapp import func_process_file

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
NOTEBOOK_LOGICAL_ID = "f898ec29-1341-b31b-4977-45a2c4d49570"
NOTEBOOK_GUID = "22222222-2222-2222-2222-222222222222"
FOLDER_ID = "33333333-3333-3333-3333-333333333333"


class _FakeFile:
    """Minimal stand-in for the File object exposing name and contents."""

    def __init__(self, name: str, contents: str) -> None:
        self.name = name
        self.contents = contents


class _FakeWorkspace:
    """Fake workspace exposing repository_items keyed by name, as the real workspace does."""

    def __init__(self, folder_id: str = "", guid: str = NOTEBOOK_GUID) -> None:
        self.workspace_id = WORKSPACE_ID
        notebook = Item(
            type="Notebook",
            name="test3",
            description="",
            guid=guid,
            logical_id=NOTEBOOK_LOGICAL_ID,
            folder_id=folder_id,
        )
        self.repository_items = {"Notebook": {"test3": notebook}}


def _reference_definition():
    """Return a definition body containing a single item reference (as in the task example)."""
    return {
        "elements": [
            {
                "elementType": "item",
                "elementId": "f5c6817f-9f02-46a9-bc6d-2a88494dc431",
                "itemType": "Notebook",
                "itemLogicalId": NOTEBOOK_LOGICAL_ID,
                "displayName": "test3",
            }
        ]
    }


def test_replaces_logical_id_with_item_id_and_workspace_folder():
    """When the item is at the workspace root, folderObjectId resolves to the workspace id."""
    workspace = _FakeWorkspace(folder_id="")
    file_obj = _FakeFile("definition.json", json.dumps(_reference_definition()))

    result = json.loads(func_process_file(workspace, None, file_obj))
    element = result["elements"][0]

    assert "itemLogicalId" not in element
    assert element["itemId"] == NOTEBOOK_GUID
    assert element["folderObjectId"] == WORKSPACE_ID
    # Non-reference keys are preserved
    assert element["elementType"] == "item"
    assert element["displayName"] == "test3"


def test_replaces_folder_object_id_with_item_folder():
    """When the item lives inside a folder, folderObjectId resolves to that folder id."""
    workspace = _FakeWorkspace(folder_id=FOLDER_ID)
    file_obj = _FakeFile("definition.json", json.dumps(_reference_definition()))

    result = json.loads(func_process_file(workspace, None, file_obj))
    element = result["elements"][0]

    assert element["itemId"] == NOTEBOOK_GUID
    assert element["folderObjectId"] == FOLDER_ID


def test_preserves_key_order():
    """The resolved itemId/folderObjectId replace itemLogicalId in place, preserving order."""
    workspace = _FakeWorkspace(folder_id="")
    file_obj = _FakeFile("definition.json", json.dumps(_reference_definition()))

    result = json.loads(func_process_file(workspace, None, file_obj))
    keys = list(result["elements"][0].keys())

    assert keys == ["elementType", "elementId", "itemType", "itemId", "folderObjectId", "displayName"]


def test_sets_ids_when_logical_id_absent():
    """A reference without itemLogicalId still gets itemId and folderObjectId set."""
    workspace = _FakeWorkspace(folder_id=FOLDER_ID)
    body = {
        "elements": [
            {
                "elementType": "item",
                "itemType": "Notebook",
                "displayName": "test3",
            }
        ]
    }
    file_obj = _FakeFile("definition.json", json.dumps(body))

    result = json.loads(func_process_file(workspace, None, file_obj))
    element = result["elements"][0]

    assert element["itemId"] == NOTEBOOK_GUID
    assert element["folderObjectId"] == FOLDER_ID


def test_overwrites_existing_ids():
    """Existing itemId/folderObjectId values are overwritten in place with the resolved ids."""
    workspace = _FakeWorkspace(folder_id=FOLDER_ID)
    body = {
        "elements": [
            {
                "elementType": "item",
                "itemType": "Notebook",
                "itemId": "stale-item-id",
                "folderObjectId": "stale-folder-id",
                "displayName": "test3",
            }
        ]
    }
    file_obj = _FakeFile("definition.json", json.dumps(body))

    result = json.loads(func_process_file(workspace, None, file_obj))
    element = result["elements"][0]

    assert element["itemId"] == NOTEBOOK_GUID
    assert element["folderObjectId"] == FOLDER_ID
    # Order is preserved when ids already exist
    assert list(element.keys()) == ["elementType", "itemType", "itemId", "folderObjectId", "displayName"]


def test_processes_nested_references():
    """References nested anywhere in the definition body are resolved."""
    workspace = _FakeWorkspace(folder_id="")
    body = {
        "audience": {
            "sections": [
                {
                    "content": {
                        "elementType": "item",
                        "itemType": "Notebook",
                        "itemLogicalId": NOTEBOOK_LOGICAL_ID,
                        "displayName": "test3",
                    }
                }
            ]
        }
    }
    file_obj = _FakeFile("definition.json", json.dumps(body))

    result = json.loads(func_process_file(workspace, None, file_obj))
    content = result["audience"]["sections"][0]["content"]

    assert content["itemId"] == NOTEBOOK_GUID
    assert content["folderObjectId"] == WORKSPACE_ID
    assert "itemLogicalId" not in content


def test_non_definition_file_is_untouched():
    """Files other than definition.json are returned unchanged."""
    workspace = _FakeWorkspace()
    original = json.dumps(_reference_definition())
    file_obj = _FakeFile(".platform", original)

    assert func_process_file(workspace, None, file_obj) == original


def test_reference_outside_repository_is_left_untouched():
    """A reference to an item not in the repository (e.g. a different workspace) is left as-is."""
    workspace = _FakeWorkspace()
    reference = {
        "elementType": "item",
        "itemType": "Notebook",
        "itemLogicalId": "99999999-9999-9999-9999-999999999999",
        "displayName": "missing",
    }
    body = {"elements": [reference]}
    file_obj = _FakeFile("definition.json", json.dumps(body))

    result = json.loads(func_process_file(workspace, None, file_obj))
    element = result["elements"][0]

    # The reference is unchanged: no resolved ids are injected and the original keys remain.
    assert element == reference


def test_reference_not_yet_deployed_raises_parsing_error():
    """A referenced item present in the repository but not yet deployed raises a ParsingError."""
    workspace = _FakeWorkspace(guid="")
    file_obj = _FakeFile("definition.json", json.dumps(_reference_definition()))

    with pytest.raises(ParsingError):
        func_process_file(workspace, None, file_obj)


def test_orgapp_audience_reference_identified_by_item_type():
    """A reference without elementType but with itemType (Org App Audience layout) is resolved."""
    workspace = _FakeWorkspace(folder_id=FOLDER_ID)
    body = {
        "audiences": [
            {
                "itemType": "Notebook",
                "itemLogicalId": NOTEBOOK_LOGICAL_ID,
                "displayName": "test3",
            }
        ]
    }
    file_obj = _FakeFile("definition.json", json.dumps(body))

    result = json.loads(func_process_file(workspace, None, file_obj))
    reference = result["audiences"][0]

    assert reference["itemId"] == NOTEBOOK_GUID
    assert reference["folderObjectId"] == FOLDER_ID
    assert "itemLogicalId" not in reference


def test_non_reference_element_is_untouched():
    """Elements that are neither elementType 'item' nor carry an itemType are left untouched."""
    workspace = _FakeWorkspace()
    body = {
        "elements": [
            {
                "elementType": "section",
                "displayName": "My Section",
            }
        ]
    }
    file_obj = _FakeFile("definition.json", json.dumps(body))

    result = json.loads(func_process_file(workspace, None, file_obj))
    element = result["elements"][0]

    assert "itemId" not in element
    assert "folderObjectId" not in element
    assert element == {"elementType": "section", "displayName": "My Section"}


def test_orgapp_audience_uses_same_processing():
    """OrgAppAudience reuses the func_process_file defined in the OrgApp module."""
    from fabric_cicd._items._orgappaudience import func_process_file as audience_func

    assert audience_func is func_process_file
