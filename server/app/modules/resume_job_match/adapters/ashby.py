from .base import AdapterSelectors, SelectorJobSourceAdapter


class AshbyAdapter(SelectorJobSourceAdapter):
    name = "ashby"
    host_suffixes = ("ashbyhq.com",)
    html_fingerprints = ("ashby_job", "ashbyhq")
    selectors = AdapterSelectors(
        title=("//*[@data-testid='job-title']", "//main//h1", "//h1"),
        company=("//*[@data-testid='company-name']", "//*[@data-testid='logo']/@alt"),
        location=("//*[@data-testid='job-location']", "//*[contains(@class, 'location')]"),
        description=(
            "//*[@data-testid='job-description']",
            "//*[contains(@class, '_descriptionText_')]",
            "//main",
        ),
    )
