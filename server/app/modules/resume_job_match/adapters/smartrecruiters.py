from .base import AdapterSelectors, SelectorJobSourceAdapter


class SmartRecruitersAdapter(SelectorJobSourceAdapter):
    name = "smartrecruiters"
    host_suffixes = ("smartrecruiters.com",)
    html_fingerprints = ("smartrecruiters", "job-sections")
    selectors = AdapterSelectors(
        title=("//*[@itemprop='title']", "//h1"),
        company=("//*[@itemprop='hiringOrganization']", "//*[@data-test='company-name']"),
        location=("//*[@itemprop='jobLocation']", "//*[@data-test='job-location']"),
        description=("//*[@itemprop='description']", "//*[contains(@class, 'job-sections')]"),
        responsibilities=("//*[@data-test='responsibilities']",),
        required_qualifications=("//*[@data-test='qualifications']",),
        preferred_qualifications=("//*[@data-test='preferred-qualifications']",),
    )
