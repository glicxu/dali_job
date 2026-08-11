"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  ClipboardList,
  FileText,
  Search,
  Target,
} from "lucide-react";
import { completeTutorial, getAuthToken } from "../lib/api";
import { AlertBanner, Button } from "./ui";

type TutorialStep = {
  title: string;
  pageLabel: string;
  href: string;
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
    title: "Save your first job",
    pageLabel: "Jobs",
    href: "/jobs",
    description: "The Jobs page keeps opportunities you want to review, analyze, and track.",
    task: "Import a job URL, import a list, or create a manual saved job.",
    icon: BriefcaseBusiness,
  },
  {
    title: "Explore Job Search",
    pageLabel: "Job Search",
    href: "/jobs/search",
    description: "Search for roles and import promising results into your saved jobs.",
    task: "Try a keyword and location search, or continue with the job you already saved.",
    icon: Search,
  },
  {
    title: "Analyze and match",
    pageLabel: "Match",
    href: "/match",
    description: "DaliJob can structure a job description and compare it with one of your resume profiles.",
    task: "Choose your resume and saved job, then run a match to review strengths and gaps.",
    icon: Target,
  },
  {
    title: "Track applications",
    pageLabel: "Applications",
    href: "/applications",
    description: "Applications connect a saved job with its status, documents, tasks, interviews, and notes.",
    task: "Open this page when you apply so DaliJob can track the rest of the process.",
    icon: ClipboardList,
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

function beginTutorial() {
  window.sessionStorage.setItem(tutorialSessionKey, "0");
  window.location.href = tutorialSteps[0].href;
}

async function finishTutorial() {
  await completeTutorial();
  window.sessionStorage.removeItem(tutorialSessionKey);
  window.location.href = "/";
}

export function TutorialStartup() {
  const [error, setError] = useState<string | null>(null);
  const [isSkipping, setIsSkipping] = useState(false);

  if (!getAuthToken()) {
    return (
      <AlertBanner tone="warning">
        Login is required to start the tutorial. <a href="/auth">Login or register</a> to continue.
      </AlertBanner>
    );
  }

  async function skipTutorial() {
    setError(null);
    setIsSkipping(true);
    try {
      await finishTutorial();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The tutorial could not be skipped.");
      setIsSkipping(false);
    }
  }

  return (
    <div className="tutorial-startup">
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <section className="tutorial-welcome-card">
        <div>
          <p className="eyebrow">First steps</p>
          <h2>Set up your job-search workspace</h2>
          <p className="summary">
            Follow a short walkthrough to add a resume, save a job, explore search, run a match,
            and learn where applications are tracked.
          </p>
        </div>
        <div className="button-row">
          <Button type="button" icon={ArrowRight} onClick={beginTutorial}>Start Tutorial</Button>
          <Button type="button" variant="ghost" loading={isSkipping} onClick={() => void skipTutorial()}>Skip Tutorial</Button>
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
        Every step is optional. Replaying or skipping this tutorial never removes or replaces your existing data.
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
  const onTargetPage = pathname === step.href || pathname.startsWith(`${step.href}/`);
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
      setError(err instanceof Error ? err.message : "The tutorial could not be completed.");
      setIsFinishing(false);
    }
  }

  return (
    <aside className="tutorial-coachmark" aria-label="DaliJob tutorial" aria-live="polite">
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
        {!isLastStep ? <Button type="button" size="compact" variant="ghost" onClick={() => moveToStep(stepIndex + 1)}>Skip Step</Button> : null}
        <Button type="button" size="compact" variant="ghost" loading={isFinishing} onClick={() => void completeAndExit()}>Skip Tutorial</Button>
      </div>
    </aside>
  );
}
