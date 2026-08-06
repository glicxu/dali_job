from .base import AdapterSelectors, SelectorJobSourceAdapter


class GreenhouseAdapter(SelectorJobSourceAdapter):
    name = "greenhouse"
    host_suffixes = ("greenhouse.io",)
    html_fingerprints = ("boards.greenhouse.io", "greenhouse-job-board", "greenhouse-job")
    selectors = AdapterSelectors(
        title=("//h1", "//*[@class='app-title']"),
        company=(
            "//*[contains(@class, 'company-name')]",
            "//*[@data-mapped='company']",
        ),
        location=(
            "//*[contains(@class, 'location')]",
            "//*[@data-mapped='location']",
        ),
        description=(
            "//*[@id='content']",
            "//*[@id='app_body']",
            "//*[contains(@class, 'job-post-content')]",
        ),
        responsibilities=("//*[@data-mapped='responsibilities']",),
        required_qualifications=("//*[@data-mapped='requirements']",),
        preferred_qualifications=("//*[@data-mapped='preferred-qualifications']",),
    )
