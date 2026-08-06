from .base import AdapterSelectors, SelectorJobSourceAdapter


class LeverAdapter(SelectorJobSourceAdapter):
    name = "lever"
    host_suffixes = ("lever.co",)
    html_fingerprints = ("lever-jobs", "posting-headline", "posting-page")
    selectors = AdapterSelectors(
        title=("//*[contains(@class, 'posting-headline')]//h2", "//h1"),
        company=(
            "//*[@data-qa='company-name']",
            "//*[contains(@class, 'main-header-logo')]//*[@alt]/@alt",
        ),
        location=(
            "//*[contains(@class, 'posting-categories')]//*[contains(@class, 'location')]",
            "//*[@data-qa='job-location']",
        ),
        description=(
            "//*[contains(@class, 'posting-page')]//*[contains(@class, 'content')]",
            "//*[contains(@class, 'section-wrapper')]",
        ),
        responsibilities=("//*[@data-qa='responsibilities']",),
        required_qualifications=("//*[@data-qa='requirements']",),
        preferred_qualifications=("//*[@data-qa='preferred-qualifications']",),
    )
