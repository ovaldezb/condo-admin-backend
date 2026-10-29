"""Garantías de configuración que no se pueden probar ejecutando código (T041).

Se leen los ``serverless.yml`` con un loader que acepta las etiquetas de CloudFormation
(``!Ref``, ``!GetAtt``, ``!Join``, ``!If``...), sin desplegar nada.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / "infra/shared/serverless.yml"
ORGANIZACIONES = ROOT / "backend/modules/organizaciones/serverless.yml"
BOUNDARY = "arn:aws:iam::${aws:accountId}:policy/condo-boundary"


class _CloudFormationLoader(yaml.SafeLoader):
    pass


def _cfn_tag(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> dict[str, Any]:
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node, deep=True)}
    assert isinstance(node, yaml.MappingNode)
    return {suffix: loader.construct_mapping(node, deep=True)}


_CloudFormationLoader.add_multi_constructor("!", _cfn_tag)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=_CloudFormationLoader)  # noqa: S506 - SafeLoader
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def shared() -> dict[str, Any]:
    return _load(SHARED)


def _resource(config: dict[str, Any], name: str) -> dict[str, Any]:
    properties = config["resources"]["Resources"][name]["Properties"]
    assert isinstance(properties, dict)
    return properties


def test_invitation_links_privacy_notice(shared: dict[str, Any]) -> None:
    template = _resource(shared, "UserPool")["AdminCreateUserConfig"]["InviteMessageTemplate"]
    assert "${param:avisoPrivacidadUrl}" in template["EmailMessage"]
    assert "{username}" in template["EmailMessage"]
    assert "{####}" in template["EmailMessage"]


def test_tenant_attribute_is_immutable_and_32_chars(shared: dict[str, Any]) -> None:
    schema = {a["Name"]: a for a in _resource(shared, "UserPool")["Schema"]}
    tenant = schema["tenant_id"]
    assert tenant["Mutable"] is False
    assert tenant["StringAttributeConstraints"] == {"MinLength": "32", "MaxLength": "32"}


def test_app_client_is_public_and_cannot_write_tenant(shared: dict[str, Any]) -> None:
    client = _resource(shared, "UserPoolClient")
    assert client["GenerateSecret"] is False
    assert client["AllowedOAuthFlows"] == ["code"]
    assert "custom:tenant_id" not in client["WriteAttributes"]


def test_temporary_password_lasts_7_days(shared: dict[str, Any]) -> None:
    policies = _resource(shared, "UserPool")["Policies"]["PasswordPolicy"]
    assert policies["TemporaryPasswordValidityDays"] == 7


def test_pre_token_generation_is_v2(shared: dict[str, Any]) -> None:
    config = _resource(shared, "UserPool")["LambdaConfig"]["PreTokenGenerationConfig"]
    assert config["LambdaVersion"] == "V2_0"


@pytest.mark.parametrize("path", [SHARED, ORGANIZACIONES],
                         ids=["cognito-triggers", "organizaciones"])
def test_lambda_roles_declare_permissions_boundary(path: Path) -> None:
    role = _load(path)["provider"]["iam"]["role"]
    assert role["permissionsBoundary"] == BOUNDARY
    assert role["name"].startswith("condo-")


@pytest.mark.parametrize("path", [SHARED, ORGANIZACIONES], ids=["shared", "organizaciones"])
def test_stacks_use_bootstrap_deployment_bucket(path: Path) -> None:
    bucket = _load(path)["provider"]["deploymentBucket"]["name"]
    assert bucket == "condo-deployments-${aws:accountId}-${aws:region}"


BOOTSTRAP = ROOT / "infra/bootstrap/serverless.yml"
_IAM_TYPES = {"AWS::IAM::OIDCProvider", "AWS::IAM::ManagedPolicy", "AWS::IAM::Role"}


def test_bootstrap_creates_iam_only_in_primary_region() -> None:
    """Una cuenta, dos regiones: IAM una sola vez (región de dev); el bucket en cada región."""
    config = _load(BOOTSTRAP)
    resources = config["resources"]["Resources"]
    for name, resource in resources.items():
        if resource["Type"] in _IAM_TYPES:
            assert resource.get("Condition") == "IsPrimaryRegion", name
    assert "Condition" not in resources["DeploymentBucket"]
    assert config["params"]["default"]["devRegion"] == "us-east-1"
    assert config["params"]["default"]["prodRegion"] == "us-west-1"


@pytest.mark.parametrize(("role", "region"), [("DeployDevRole", "devRegion"),
                                              ("DeployProdRole", "prodRegion")])
def test_each_deploy_role_only_reaches_its_region_bucket(role: str, region: str) -> None:
    resources = _load(BOOTSTRAP)["resources"]["Resources"]
    statements = resources[role]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    buckets = {r for s in statements for r in s["Resource"]}
    assert buckets == {
        f"arn:aws:s3:::condo-deployments-${{aws:accountId}}-${{param:{region}}}",
        f"arn:aws:s3:::condo-deployments-${{aws:accountId}}-${{param:{region}}}/*",
    }
