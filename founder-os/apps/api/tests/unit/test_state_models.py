"""State Engine ORM registration (arch §1): 4 tables on the shared Base."""


def test_state_tables_registered_on_base():
    import app.state.models  # noqa: F401
    from app.database import Base

    tables = Base.metadata.tables
    for name in (
        "state_sources",
        "state_observations",
        "company_state_entities",
        "state_relations",
    ):
        assert name in tables, f"missing table {name}"


def test_entity_columns_and_defaults():
    import app.state.models as m

    cols = m.CompanyStateEntity.__table__.c
    assert cols.confidence.server_default is not None
    assert cols.pinned.server_default is not None
    assert cols.is_active.server_default is not None
    assert cols.embedding.type.dim == 1536
    # provenance feed values are CHECK-constrained now (later feeds need no migration)
    checks = [str(c.sqltext) for c in m.CompanyStateEntity.__table__.constraints
              if hasattr(c, "sqltext")]
    assert any("user_doc" in c and "system" in c for c in checks)


def test_observation_dedup_constraint_present():
    import app.state.models as m

    uqs = [c.name for c in m.StateObservation.__table__.constraints]
    assert "uq_state_obs_dedup" in uqs
