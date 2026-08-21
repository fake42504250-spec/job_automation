from job_automation.contacts import contacts_from_text, valid_corporate_email


def test_public_contact_extraction_prefers_role_address():
    contacts = contacts_from_text("Write to careers@acme.test or person@gmail.com")
    assert [item.email for item in contacts] == ["careers@acme.test"]
    assert contacts[0].confidence == 90


def test_personal_email_is_rejected():
    assert not valid_corporate_email("candidate@gmail.com")
    assert valid_corporate_email("talent@company.co.in")

