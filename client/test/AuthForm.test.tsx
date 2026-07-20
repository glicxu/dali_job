import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthForm } from "../components/AuthForm";
import * as api from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    clearAuthToken: vi.fn(),
    getAuthToken: vi.fn(),
    getCurrentUser: vi.fn(),
    loginUser: vi.fn(),
    registerUser: vi.fn(),
  };
});

const user = {
  id: 7,
  email: "candidate@example.com",
  display_name: "Candidate",
  workspace_id: 11,
};

describe("AuthForm", () => {
  beforeEach(() => {
    vi.mocked(api.getAuthToken).mockReturnValue(null);
  });

  it("logs in and reports the authenticated user", async () => {
    vi.mocked(api.loginUser).mockResolvedValue({ access_token: "token", token_type: "bearer", user });
    const onAuthChange = vi.fn();
    const actor = userEvent.setup();
    render(<AuthForm onAuthChange={onAuthChange} />);

    await actor.type(screen.getByLabelText("Email"), user.email);
    await actor.type(screen.getByLabelText("Password"), "correct horse battery staple");
    await actor.click(screen.getAllByRole("button", { name: "Login" })[1]);

    expect(await screen.findByText("Signed in.")).toBeInTheDocument();
    expect(screen.getByText(user.email)).toBeInTheDocument();
    expect(api.loginUser).toHaveBeenCalledWith(user.email, "correct horse battery staple");
    expect(onAuthChange).toHaveBeenCalledWith(user);
  });

  it("registers with a display name", async () => {
    vi.mocked(api.registerUser).mockResolvedValue({ access_token: "token", token_type: "bearer", user });
    const actor = userEvent.setup();
    render(<AuthForm />);

    await actor.click(screen.getByRole("button", { name: "Register" }));
    await actor.type(screen.getByLabelText("Email"), user.email);
    await actor.type(screen.getByLabelText("Display Name"), user.display_name);
    await actor.type(screen.getByLabelText("Password"), "correct horse battery staple");
    await actor.click(screen.getByRole("button", { name: "Create Account" }));

    expect(await screen.findByText("Account created.")).toBeInTheDocument();
    expect(api.registerUser).toHaveBeenCalledWith(
      user.email,
      "correct horse battery staple",
      user.display_name,
    );
  });

  it("clears an invalid stored session", async () => {
    vi.mocked(api.getAuthToken).mockReturnValue("expired-token");
    vi.mocked(api.getCurrentUser).mockRejectedValue(new Error("expired"));
    render(<AuthForm />);

    await waitFor(() => expect(api.clearAuthToken).toHaveBeenCalledOnce());
    expect(screen.getAllByRole("button", { name: "Login" })).toHaveLength(2);
  });
});
