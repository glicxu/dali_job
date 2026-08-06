from .base import AdapterSelectors, SelectorJobSourceAdapter


class IcimsAdapter(SelectorJobSourceAdapter):
    name = "icims"
    host_suffixes = ("icims.com",)
    html_fingerprints = ("icims_job", "icims_jobcontent", "icims-header")
    selectors = AdapterSelectors(
        title=("//*[contains(@class, 'iCIMS_JobHeader')]//h1", "//*[@itemprop='title']", "//h1"),
        company=("//*[@itemprop='hiringOrganization']", "//*[contains(@class, 'iCIMS_CompanyName')]"),
        location=("//*[@itemprop='jobLocation']", "//*[contains(@class, 'iCIMS_JobLocation')]"),
        description=(
            "//*[@id='job-description']",
            "//*[contains(@class, 'iCIMS_JobContent')]",
            "//*[@itemprop='description']",
        ),
    )
