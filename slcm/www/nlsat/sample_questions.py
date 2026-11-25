"""/nlsat/sample-questions — sample question papers (as links), written by the Admissions
Office in Applicant Portal Config (Sample Question Paper, per portal)."""

from slcm.admission.utils.portal_pages import prepare_sidebar_page

no_cache = 1


def get_context(context):
	pages = prepare_sidebar_page(context, "sample_questions", "/nlsat/sample-questions")
	context.title = "Sample Questions"
	context.page_subtitle = "Prepare for the entrance test with sample question papers."
	context.page_content = pages.sample_question_content
	return context
