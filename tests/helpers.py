def find_item(client, name: str) -> dict:
    return next(i for i in client.get("/menu/items").json() if i["name"] == name)


def modifier_id(client, item_id: int, modifier_name: str) -> int:
    detail = client.get(f"/menu/items/{item_id}").json()
    for group in detail["modifier_groups"]:
        for m in group["modifiers"]:
            if m["name"] == modifier_name:
                return m["id"]
    raise KeyError(modifier_name)


def free_table(client) -> dict:
    return client.get("/tables", params={"status": "free"}).json()[0]
