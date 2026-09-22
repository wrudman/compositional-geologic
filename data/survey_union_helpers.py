"""Single-union survey policy; all updates preserve undo snapshots."""
import tools_human as tools


def merge_selection_error(regions, unions):
    if len(regions) < 2:
        return "Select two or more regions connected through shared edges."
    if len(unions) > 1:
        return "Remove the extra unions first. Only one union is allowed per diagram."
    if unions and not any(region is unions[0]["face"] for region in regions):
        return "Only one union is allowed. Select the existing union and the regions you want to add."
    return ""


def prepare_merge(regions, unions):
    error = merge_selection_error(regions, unions)
    if error:
        raise ValueError(error)
    existing = unions[0] if unions else None
    sources = []
    for region in regions:
        # Older sessions may have unions without source_faces metadata.
        if existing and region is existing["face"]:
            sources.extend(existing["pair"])
        else:
            sources.append(region)
    face = tools.merge(*sources)
    return face, tuple(sources), existing


def replace_union(state, record, existing):
    """Replace, never mutate, records referenced by shallow undo snapshots."""
    if existing:
        old_face = existing["face"]
        state["annotations"] = [
            {**annotation, "obj": record["face"]}
            if annotation.get("obj") is old_face else annotation
            for annotation in state["annotations"]
        ]
    state["unions"] = [record]
    state["union_consumed"] = list(record["pair"])
