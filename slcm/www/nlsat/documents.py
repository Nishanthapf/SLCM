"""/nlsat/documents — documents the applicant must keep ready, written by the Admissions
Office in Applicant Portal Config (Document Upload Instructions, per portal)."""

from slcm.admission.utils.portal_pages import prepare_sidebar_page

no_cache = 1


def get_context(context):
	pages = prepare_sidebar_page(context, "documents", "/nlsat/documents")
	context.title = "Documents"
	context.page_subtitle = "Documents you will need to upload with your application, and the formats we accept."
	context.page_content = pages.document_content
	return context
