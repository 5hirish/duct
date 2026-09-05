"use client";

// The card for whatever the run is parked on. Three pauses exist and they
// resolve through one answer endpoint; the event name is what picks the card,
// and the card decides the answer's shape. Adding a fourth pause is one entry
// here — the hook, the reducer and the route already carry any event with an
// `interrupt_id`.

import { AgentEvent } from "../../lib/agentEvents";
import AccountSelect from "../insights/AccountSelect";
import ConnectionRequest from "../insights/ConnectionRequest";
import QuestionsCard from "./QuestionsCard";

const CARDS = {
  [AgentEvent.QUESTIONS_REQUIRED]: ({ pause, onAnswer, disabled, questionsCopy }) => (
    <QuestionsCard questions={pause.questions || []} onSubmit={onAnswer} disabled={disabled} {...questionsCopy} />
  ),
  [AgentEvent.CONNECTION_REQUIRED]: ({ pause, onAnswer, disabled }) => (
    <ConnectionRequest request={pause} onAnswer={onAnswer} disabled={disabled} />
  ),
  [AgentEvent.ACCOUNT_SELECTION_REQUIRED]: ({ pause, onAnswer, disabled }) => (
    <AccountSelect request={pause} onAnswer={onAnswer} disabled={disabled} />
  ),
};

export default function PauseCard({ pause, onAnswer, disabled = false, questionsCopy }) {
  if (!pause) return null;
  const Card = CARDS[pause.event];
  if (!Card) return null;
  // Keyed on the pause identity so a second question gets fresh local state
  // rather than the previous card's half-filled answers.
  return <Card key={pause.interrupt_id || pause.event} pause={pause} onAnswer={onAnswer} disabled={disabled} questionsCopy={questionsCopy} />;
}
