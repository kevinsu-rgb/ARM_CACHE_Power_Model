import dataclasses

import pytest

from power.config import (HPI_FALLBACK_CORE, ConfigError, config_from_dict, config_hash,
                          config_to_dict, implied_vdd, validate)
from helpers import base_cfg


def test_implied_vdd_table():
    assert implied_vdd(28, "LOP") == pytest.approx(0.6)
    assert implied_vdd(28, "HP") == pytest.approx(0.86)
    assert implied_vdd(28, "LSTP") == pytest.approx(0.92)
    assert implied_vdd(45, "HP") == pytest.approx(1.0)


@pytest.mark.parametrize("field,value", [("tech_node_nm", 21), ("tech_node_nm", 91),
    ("device_type", "XX"), ("num_cores", 0), ("clock_mhz", 0), ("temperature_k", 0),
    ("cpu_type", "KVM")])
def test_validate_rejects(field, value):
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(base_cfg(), **{field: value}))


def test_validate_accepts_base_and_fallback():
    validate(base_cfg())
    validate(dataclasses.replace(base_cfg(), cpu_type="MINOR", core=HPI_FALLBACK_CORE))
    validate(dataclasses.replace(base_cfg(), cpu_type="TIMING", core=HPI_FALLBACK_CORE))


def test_validate_core_kind_mismatch_and_caches():
    c = base_cfg()
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(c, cpu_type="MINOR"))
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(c, cpu_type="O3", core=HPI_FALLBACK_CORE))
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(c, caches=c.caches[:3]))
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(c, caches=(c.caches[1], c.caches[0]) + c.caches[2:]))
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(c, caches=(dataclasses.replace(c.caches[0], assoc=0),) + c.caches[1:]))


def test_implied_vdd_nodes_and_errors():
    assert implied_vdd(90, "LSTP") == pytest.approx(1.3)
    assert implied_vdd(22, "HP") == pytest.approx(0.8)
    with pytest.raises(ConfigError):
        implied_vdd(21, "HP")
    with pytest.raises(ConfigError):
        implied_vdd(28, "XX")


def test_hash_stable_and_sensitive():
    c = base_cfg()
    h = config_hash(c, "abc", 1)
    assert h == config_hash(config_from_dict(config_to_dict(c)), "abc", 1)
    assert len(h) == 16
    variants = [dataclasses.replace(c, num_cores=2), dataclasses.replace(c, clock_mhz=2000),
                dataclasses.replace(c, device_type="HP"), dataclasses.replace(c, temperature_k=340),
                dataclasses.replace(c, caches=(c.caches[0], c.caches[1],
                    dataclasses.replace(c.caches[2], size_bytes=1 << 20), c.caches[3])),
                dataclasses.replace(c, core=dataclasses.replace(c.core, model="neoverse_v2"))]
    hashes = {config_hash(v, "abc", 1) for v in variants} | {h, config_hash(c, "def", 1), config_hash(c, "abc", 2)}
    assert len(hashes) == len(variants) + 3


@pytest.mark.parametrize("t", [299, 305, 350.5, 410, 290])
def test_validate_rejects_bad_temperature(t):
    with pytest.raises(ConfigError):
        validate(dataclasses.replace(base_cfg(), temperature_k=t))


@pytest.mark.parametrize("t", [300, 350, 400])
def test_validate_accepts_good_temperature(t):
    validate(dataclasses.replace(base_cfg(), temperature_k=t))
