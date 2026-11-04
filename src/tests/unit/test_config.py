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


def _with_cache(name, **kw):
    c = base_cfg()
    return dataclasses.replace(c, caches=tuple(
        dataclasses.replace(x, **kw) if x.name == name else x for x in c.caches))


@pytest.mark.parametrize("name,kw,field,value", [
    ("l2", {"assoc": 12}, "assoc", 12),
    ("l1d", {"assoc": 3}, "assoc", 3),
    ("l3", {"block_size": 48}, "block_size", 48),
    ("l2", {"size_bytes": 768 * 1024}, "size_bytes", 768 * 1024),      # 768 sets
    ("l1i", {"size_bytes": 32768 + 64}, "size_bytes", 32768 + 64),     # not divisible
    ("l1i", {"size_bytes": 256, "assoc": 8}, "size_bytes", 256),       # 0.5 sets
])
def test_validate_rejects_non_power_of_two_geometry(name, kw, field, value):
    from power.config import GeometryError
    with pytest.raises(GeometryError) as ei:
        validate(_with_cache(name, **kw))
    e = ei.value
    assert isinstance(e, ConfigError)
    assert (e.cache, e.field, e.value) == (name, field, value)
    assert name in str(e) and str(value) in str(e) and "power of two" in str(e)


@pytest.mark.parametrize("name,kw", [
    ("l1d", {"assoc": 1}), ("l1d", {"assoc": 2}), ("l2", {"assoc": 4}),
    ("l2", {"size_bytes": 512 * 1024}), ("l3", {"size_bytes": 4 << 20, "assoc": 16}),
    ("l1i", {"block_size": 128}),
])
def test_validate_accepts_power_of_two_geometry(name, kw):
    validate(_with_cache(name, **kw))
