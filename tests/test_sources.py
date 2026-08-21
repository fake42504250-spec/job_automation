from job_automation.job_sources import parse_job_alert_html, unwrap_redirect


def test_redirect_is_unwrapped():
    assert (
        unwrap_redirect("https://alerts.example/redirect?url=https%3A%2F%2Facme.test%2Fjobs%2F1")
        == "https://acme.test/jobs/1"
    )


def test_job_alert_parser_ignores_unsubscribe():
    html = """
    <div><a href="https://acme.test/jobs/backend-intern">Backend Engineer Intern at Acme</a></div>
    <a href="https://alerts.test/unsubscribe">Unsubscribe</a>
    """
    leads = parse_job_alert_html(html, "New jobs", "message-1")
    assert len(leads) == 1
    assert leads[0].company == "Acme"
    assert leads[0].source_message_id == "message-1"

