from media_mail import MailRoute, MediaIntake, MediaWorkflow


class FakeClient:
    def __init__(self):
        self.records = []

    def zone(self, domain):
        assert domain == "studio.example"
        return "zone-42"

    def set_mx(self, zone_id, name, host, priority):
        self.records.append((zone_id, name, host, priority))

    def sending_domains(self):
        return [{"domain": "studio.example"}]


def test_intake_orders_mx_and_moves_asset_to_delivery():
    client = FakeClient()
    workflow = MediaWorkflow(client)
    intake = MediaIntake(
        asset_id="clip-17", creator_email="editor@example.com",
        source_uri="s3://studio/clips/17.mov", domain="studio.example",
        mx_name="studio.example", routes=[
            MailRoute(host="backup.mail.example", priority=20),
            MailRoute(host="primary.mail.example", priority=10),
        ],
    )
    result = workflow.ingest(intake)
    assert result["job"].primary_mx == "primary.mail.example"
    assert result["job"].state == "queued"
    assert result["sending_domains"] == [{"domain": "studio.example"}]
    assert client.records == [
        ("zone-42", "studio.example", "primary.mail.example", 10),
        ("zone-42", "studio.example", "backup.mail.example", 20),
    ]
    assert workflow.advance("clip-17").state == "processed"
    assert workflow.deliver("clip-17").state == "delivered"
    workflow.ingest(intake)
    assert len(client.records) == 2


def test_intake_rejects_empty_zone_before_writes():
    import pytest

    for zone_id in ("", "   ", None):
        client = FakeClient()
        client.zone = lambda domain: zone_id
        workflow = MediaWorkflow(client)
        intake = MediaIntake(
            asset_id="missing-zone", creator_email="editor@example.com",
            source_uri="s3://studio/clip.mov", domain="studio.example",
            mx_name="studio.example",
            routes=[MailRoute(host="primary.mail.example", priority=10)],
        )
        with pytest.raises(ValueError, match="no registered DNS zone"):
            workflow.ingest(intake)
        assert client.records == []
        assert workflow.jobs == {}
