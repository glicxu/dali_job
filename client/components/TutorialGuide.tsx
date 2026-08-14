"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  FileText,
  Search,
} from "lucide-react";
import { completeTutorial, getAuthToken } from "../lib/api";
import { AlertBanner, Button } from "./ui";

type TutorialStep = {
  title: string;
  pageLabel: string;
  href: string;
  allowedPaths?: string[];
  description: string;
  task: string;
  icon: typeof FileText;
};

const tutorialSessionKey = "dalijob_tutorial_step";

const tutorialSteps: TutorialStep[] = [
  {
    title: "Add your resume",
    pageLabel: "Resumes",
    href: "/profile",
    description: "Start with the resume DaliJob will use to understand your experience and skills.",
    task: "Import a PDF for automatic analysis, or manually create a resume profile.",
    icon: FileText,
  },
  {
    title: "Explore Job Search",
    pageLabel: "Job Search",
    href: "/jobs/search",
    description: "Search for roles and save a promising result so you can review it before matching.",
    task: "Run a keyword and location search, select a result, and save it without using the immediate-match option.",
    icon: Search,
  },
  {
    title: "View Saved Jobs and Match",
    pageLabel: "Saved Jobs",
    href: "/jobs",
    allowedPaths: ["/jobs", "/match"],
    description: "Review the jobs you saved from search and compare one with your resume.",
    task: "Open a saved job, analyze its job profile if needed, then match it with your resume to review strengths and gaps.",
    icon: BriefcaseBusiness,
  },
];

function readTutorialStep(): number | null {
  if (typeof window === "undefined") return null;
  const rawValue = window.sessionStorage.getItem(tutorialSessionKey);
  if (rawValue === null) return null;
  const parsed = Number(rawValue);
  return Number.isInteger(parsed) && parsed >= 0 && parsed < tutorialSteps.length ? parsed : null;
}

export function isTutorialActive(): boolean {
  return readTutorialStep() !== null;
}

function isPathAllowedForStep(pathname: string, step: TutorialStep): boolean {
  const allowedPaths = step.allowedPaths ?? [step.href];
  return allowedPaths.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export function isTutorialRouteAllowed(pathname: string): boolean {
  if (pathname === "/tutorial") return true;
  const stepIndex = readTutorialStep();
  if (stepIndex === null) return pathname === "/";
  return isPathAllowedForStep(pathname, tutorialSteps[stepIndex]);
}

export function tutorialRouteFallback(): string {
  const stepIndex = readTutorialStep();
  return stepIndex === null ? "/" : tutorialSteps[stepIndex].href;
}

function beginTutorial() {
  window.sessionStorage.setItem(tutorialSessionKey, "0");
  window.location.href = tutorialSteps[0].href;
}

async function finishTutorial() {
  await completeTutorial();
  window.sessionStorage.removeItem(tutorialSessionKey);
  window.location.href = "/dashboard";
}

function postponeTutorial() {
  window.sessionStorage.removeItem(tutorialSessionKey);
  window.location.href = "/";
}

export function TutorialStartup() {
  if (!getAuthToken()) {
    return (
      <AlertBanner tone="warning">
        Login is required to use Getting Started. <a href="/auth">Login or register</a> to continue.
      </AlertBanner>
    );
  }

  return (
    <div className="tutorial-startup">
      <section className="tutorial-welcome-card">
        <div>
          <p className="eyebrow">First steps</p>
          <h2>Set up your job-search workspace</h2>
          <p className="summary">
            Follow a short walkthrough to add a resume, find and save a job through Job Search,
            then match it from Saved Jobs.
          </p>
        </div>
        <div className="button-row">
          <Button type="button" icon={ArrowRight} onClick={beginTutorial}>Begin</Button>
          <Button type="button" variant="ghost" onClick={postponeTutorial}>Skip Getting Started</Button>
        </div>
      </section>

      <ol className="tutorial-step-overview">
        {tutorialSteps.map((step, index) => {
          const Icon = step.icon;
          return (
            <li key={step.href}>
              <span className="tutorial-overview-icon"><Icon size={19} aria-hidden="true" /></span>
              <div><strong>{index + 1}. {step.title}</strong><span>{step.description}</span></div>
            </li>
          );
        })}
      </ol>

      <p className="metadata tutorial-data-note">
        You can postpone Getting Started without changing your data. Your account remains in first-time setup until you finish every step once.
      </p>
    </div>
  );
}

export function TutorialCoachmark() {
  const pathname = usePathname();
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isFinishing, setIsFinishing] = useState(false);

  useEffect(() => {
    setStepIndex(readTutorialStep());
  }, [pathname]);

  if (stepIndex === null || pathname === "/tutorial") return null;

  const step = tutorialSteps[stepIndex];
  const Icon = step.icon;
  const onTargetPage = isPathAllowedForStep(pathname, step);
  const isLastStep = stepIndex === tutorialSteps.length - 1;

  function moveToStep(nextIndex: number) {
    if (nextIndex >= tutorialSteps.length) {
      void completeAndExit();
      return;
    }
    window.sessionStorage.setItem(tutorialSessionKey, String(nextIndex));
    setStepIndex(nextIndex);
    window.location.href = tutorialSteps[nextIndex].href;
  }

  async function completeAndExit() {
    setError(null);
    setIsFinishing(true);
    try {
      await finishTutorial();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Getting Started could not be completed.");
      setIsFinishing(false);
    }
  }

  return (
    <aside className="tutorial-coachmark" aria-label="DaliJob Getting Started guide" aria-live="polite">
      <div className="tutorial-progress-track" aria-hidden="true">
        <span style={{ width: `${((stepIndex + 1) / tutorialSteps.length) * 100}%` }} />
      </div>
      <div className="tutorial-coachmark-heading">
        <span className="tutorial-coachmark-icon"><Icon size={20} aria-hidden="true" /></span>
        <div><p>Step {stepIndex + 1} of {tutorialSteps.length}</p><h2>{step.title}</h2></div>
      </div>
      <p>{step.description}</p>
      <p className="tutorial-task"><strong>Try this:</strong> {step.task}</p>
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <div className="tutorial-coachmark-actions">
        {!onTargetPage ? (
          <Button type="button" size="compact" onClick={() => { window.location.href = step.href; }}>Open {step.pageLabel}</Button>
        ) : (
          <Button type="button" size="compact" icon={isLastStep ? CheckCircle2 : ArrowRight} loading={isFinishing} onClick={() => moveToStep(stepIndex + 1)}>
            {isLastStep ? "Finish" : "Next"}
          </Button>
        )}
        {!isLastStep ? (
          <Button type="button" size="compact" variant="ghost" onClick={postponeTutorial}>Skip Getting Started</Button>
        ) : null}
      </div>
    </aside>
  );
}
