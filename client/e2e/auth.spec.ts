import { expect, test } from "@playwright/test";

const currentUser = {
  id: 7,
  email: "candidate@example.com",
  display_name: "Candidate",
  workspace_id: 11,
};

test.beforeEach(async ({ page }) => {
  await page.route("http://localhost:5010/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/auth/login") || url.pathname.endsWith("/auth/register")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ access_token: "browser-test-token", token_type: "bearer", user: currentUser }),
      });
      return;
    }
    if (url.pathname.endsWith("/me")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(currentUser) });
      return;
    }
    if (url.pathname.endsWith("/dashboard")) {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          recommended_next_step: { label: "Add a resume", reason: "Build your profile.", href: "/profile" },
          setup_alerts: [],
          application_actions: [],
          best_matches: [],
          recently_saved_jobs: [],
        }),
      });
      return;
    }
    await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not mocked" }) });
  });
});

test("registration, authenticated navigation, and logout", async ({ page }) => {
  await page.goto("/auth");
  await page.getByRole("button", { name: "Register" }).click();
  await page.getByLabel("Email").fill(currentUser.email);
  await page.getByLabel("Display Name").fill(currentUser.display_name);
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Create Account" }).click();

  await expect(page.getByLabel("Primary navigation")).toBeVisible();
  await expect(page.getByLabel("Primary navigation").getByText(currentUser.email)).toBeVisible();
  await page.getByRole("link", { name: "Home" }).click();
  await expect(page.getByRole("heading", { name: "DaliJob dashboard" })).toBeVisible();

  await page.getByRole("button", { name: "Sign Out" }).click();
  await expect(page.getByLabel("Public navigation")).toBeVisible();
  await expect(page.getByLabel("Public navigation").getByRole("link", { name: "Login / Register" })).toBeVisible();
});

test("core public routes render without a client crash", async ({ page }) => {
  for (const path of [
    "/",
    "/profile",
    "/match",
    "/jobs",
    "/jobs/manual",
    "/jobs/import-url",
    "/jobs/search",
    "/applications",
    "/documents",
    "/materials",
    "/interviews",
    "/analytics",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByText("Application error: a client-side exception has occurred")).toHaveCount(0);
  }
});
