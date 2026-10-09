import yaml

def load_policy(path="policy.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

def check_access(policy, role, resource):
    res = policy.get("resources", {}).get(resource)
    if res is None:
        return False, "unknown resource (default deny)"
    if role in res.get("allowed_roles", []):
        return True, "role allowed"
    return False, "role not allowed (default deny)"