from .base import AdapterSelectors, SelectorJobSourceAdapter


class WorkdayAdapter(SelectorJobSourceAdapter):
    name = "workday"
    host_suffixes = ("myworkdayjobs.com", "workdayjobs.com")
    html_fingerprints = ("data-automation-id=\"jobposting", "workday job posting")
    selectors = AdapterSelectors(
        title=("//*[@data-automation-id='jobPostingHeader']", "//h1"),
        company=("//*[@data-automation-id='company']", "//*[@data-automation-id='logo']/@alt"),
        location=(
            "//*[@data-automation-id='locations']",
            "//*[@data-automation-id='jobPostingLocation']",
        ),
        description=(
            "//*[@data-automation-id='jobPostingDescription']",
            "//*[@data-automation-id='jobPostingDetails']",
        ),
    )
