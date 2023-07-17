"This script generates a single JSON file containing all the docs and metadata for connections."
from pathlib import Path
from subprocess import check_output

import json
import yaml

connections = {}
connections_dir = Path("connections")

# parse all .yml files in the connections directory and store them in `connections`
for path in connections_dir.glob("**/*.yml"):
    print(f"Loading connection from {path}")
    with open(path, mode="r", encoding="utf-8") as f:
        connection = yaml.safe_load(f)
        connection["file_path"] = str(path)

        # get the last commit date for the connection
        commit_date = check_output(
            f"git log -1 --pretty=format:%cI {path}".split()
        ).decode()
        connection["last_commit_date"] = commit_date

        # if there are any parameters with an example value, make sure the example value is a string
        for parameter in connection.get("parameters", []):
            if "example" in parameter:
                parameter["example"] = str(parameter["example"])

        connections[connection["id"]] = connection

print(f"Loaded {len(connections)} connections. Checking for inheritance...\n")

full_connections: dict[str, dict] = {}

# then we need to deal with inheritance
for connection in connections.values():
    new_conn = connection.copy()

    if "inherit_from" in new_conn:
        print(f"Connection {new_conn['id']} inherits from {new_conn['inherit_from']}")

        # if this connection extends another connection, we need to merge the two
        # we do this by copying all the fields from the parent connection into the child connection
        parent = connections[new_conn["inherit_from"]]
        for key, value in parent.items():
            # if the key is `+parameters`, we need to merge the parameters. we do this later
            if key == "+parameters":
                continue

            # otherwise, we just copy the value from the parent connection
            if key not in new_conn:
                print(f"\tAdding {key} to {new_conn['id']}")
                new_conn[key] = value

        # if there's a `+parameters` field in the child connection, we need to merge it
        # with the parameters from the parent connection
        if "+parameters" in new_conn:
            print(f"\tMerging parameters from {new_conn['inherit_from']}")
            new_params = parent["parameters"]
            for parameter in new_conn["+parameters"]:
                # if the parameter airflow_param_name is already in the parent connection,
                # delete it
                if any(
                    [
                        p["airflow_param_name"] == parameter["airflow_param_name"]
                        and p.get("in_extra", False) == parameter.get("in_extra", False)
                        for p in new_params
                    ]
                ):
                    new_params = [
                        p
                        for p in new_params
                        if not (
                            p["airflow_param_name"] == parameter["airflow_param_name"]
                            and p.get("in_extra", False)
                            == parameter.get("in_extra", False)
                        )
                    ]

                # then add the parameter to the parent connection
                print(
                    f"\t\tAdding parameter {parameter['airflow_param_name']} to {new_conn['inherit_from']}"
                )
                new_params.append(parameter)

            # then delete the `+parameters` field from the child connection
            print(f"\tRemoving `+parameters` from {new_conn['id']}")
            del new_conn["+parameters"]

            # and finally, set the parent connection's parameters to the new parameters
            new_conn["parameters"] = new_params

        # and then we need to remove the `inherit_from` field from the child connection
        print(f"Removing `inherit_from` from {new_conn['id']}\n")
        del new_conn["inherit_from"]

    # and finally, we add the connection to the full connections dict
    full_connections[new_conn["id"]] = new_conn

print("Removing non-visible connections...")

full_visible_connections = []
for connection in full_connections.values():
    if connection.get("visible", True):
        full_visible_connections.append(connection)

print("Done removing non-visible connections.\n")

# finally, we write the connections to a single JSON file
with open("connections.json", mode="w", encoding="utf-8") as f:
    print("Writing connections to connections.json")
    json.dump(full_visible_connections, f, indent=4)
