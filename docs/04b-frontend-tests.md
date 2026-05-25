# 04b · Frontend Test Specifications (Concrete)

Companion to `04-test-specifications.md`, covering the Jest + React Native Testing
Library suites. Native modules (`expo-notifications`, navigation, the API client)
are mocked. Preserve each test's intent.

Shared mock setup:
```tsx
// frontend/__tests__/setup.ts
jest.mock("expo-notifications", () => ({
  getExpoPushTokenAsync: jest.fn(async () => ({ data: "ExponentPushToken[xyz]" })),
  requestPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
  getPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
  setNotificationHandler: jest.fn(),
}));
```

---

## M3 — Onboarding

### `FE-ONBOARD-VALIDATION-01`
Submit disabled until at least one room exists.
```tsx
import { render, fireEvent } from "@testing-library/react-native";
import OnboardingScreen from "../src/screens/OnboardingScreen";

test("generate button disabled with no rooms", () => {
  const { getByTestId } = render(<OnboardingScreen />);
  expect(getByTestId("generate-btn").props.accessibilityState.disabled).toBe(true);
});

test("generate button enabled after adding a room", () => {
  const { getByTestId, getByPlaceholderText } = render(<OnboardingScreen />);
  fireEvent.press(getByTestId("add-room-btn"));
  fireEvent.changeText(getByPlaceholderText("Room name"), "Kitchen");
  fireEvent.changeText(getByPlaceholderText("Floor type"), "Tile");
  expect(getByTestId("generate-btn").props.accessibilityState.disabled).toBe(false);
});
```

### `FE-ONBOARD-ROOMBUILDER-01`
Rooms can be added and removed dynamically.
```tsx
import { render, fireEvent } from "@testing-library/react-native";
import OnboardingScreen from "../src/screens/OnboardingScreen";

test("room rows add and remove", () => {
  const { getByTestId, queryAllByTestId } = render(<OnboardingScreen />);
  fireEvent.press(getByTestId("add-room-btn"));
  fireEvent.press(getByTestId("add-room-btn"));
  expect(queryAllByTestId(/room-row-/).length).toBe(2);
  fireEvent.press(getByTestId("remove-room-0"));
  expect(queryAllByTestId(/room-row-/).length).toBe(1);
});
```

### `FE-ONBOARD-SUBMIT-PAYLOAD-01`
Submitting assembles the contract-shaped payload and calls the client.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import OnboardingScreen from "../src/screens/OnboardingScreen";
import * as api from "../src/api/client";

test("submit posts a well-formed onboard payload", async () => {
  const spy = jest.spyOn(api, "onboardHome").mockResolvedValue({
    home_id: "h1", name: "Apartment", confidence_score: 0.8, rooms: [] });
  const { getByTestId, getByPlaceholderText } = render(<OnboardingScreen />);
  fireEvent.press(getByTestId("add-room-btn"));
  fireEvent.changeText(getByPlaceholderText("Room name"), "Kitchen");
  fireEvent.changeText(getByPlaceholderText("Floor type"), "Tile");
  fireEvent.changeText(getByTestId("notes-input"), "light upkeep");
  fireEvent.press(getByTestId("generate-btn"));
  await waitFor(() => expect(spy).toHaveBeenCalled());
  const payload = spy.mock.calls[0][0];
  expect(payload.name).toBeTruthy();
  expect(payload.description_text).toContain("Kitchen");
  expect(payload.description_text).toContain("Tile");
});
```

### `FE-API-ERROR-SURFACE-01`
A failed onboard surfaces an error message, not a crash.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import OnboardingScreen from "../src/screens/OnboardingScreen";
import * as api from "../src/api/client";

test("onboard failure shows an error banner", async () => {
  jest.spyOn(api, "onboardHome").mockRejectedValue(new Error("schedule_generation_failed"));
  const { getByTestId, getByPlaceholderText, findByTestId } = render(<OnboardingScreen />);
  fireEvent.press(getByTestId("add-room-btn"));
  fireEvent.changeText(getByPlaceholderText("Room name"), "Kitchen");
  fireEvent.changeText(getByPlaceholderText("Floor type"), "Tile");
  fireEvent.press(getByTestId("generate-btn"));
  expect(await findByTestId("error-banner")).toBeTruthy();
});
```

### `FE-ONBOARD-VISION-HIDDEN-01`
When the backend reports vision is off, the scan button is not rendered.
```tsx
import { render, waitFor } from "@testing-library/react-native";
import OnboardingScreen from "../src/screens/OnboardingScreen";
import * as api from "../src/api/client";

test("scan button hidden when vision disabled", async () => {
  jest.spyOn(api, "getCapabilities").mockResolvedValue({
    vision_onboarding: false, vision_model: null });
  const { queryByTestId } = render(<OnboardingScreen />);
  await waitFor(() => expect(api.getCapabilities).toHaveBeenCalled());
  expect(queryByTestId("scan-blueprint-btn")).toBeNull();
});
```

### `FE-ONBOARD-VISION-PREFILL-01`
When vision is on, scanning an image pre-fills the editable description.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import OnboardingScreen from "../src/screens/OnboardingScreen";
import * as api from "../src/api/client";

jest.mock("expo-image-picker", () => ({
  launchImageLibraryAsync: jest.fn(async () => ({
    canceled: false,
    assets: [{ uri: "file:///plan.png", base64: "iVBORw0KGgo=" }] })),
  requestMediaLibraryPermissionsAsync: jest.fn(async () => ({ status: "granted" })),
}));

test("scanning prefills description text the user can edit", async () => {
  jest.spyOn(api, "getCapabilities").mockResolvedValue({
    vision_onboarding: true, vision_model: "google/gemini-2.5-flash" });
  jest.spyOn(api, "describeFromImage").mockResolvedValue({
    description_text: "Two carpeted bedrooms and a tiled kitchen." });
  const { getByTestId } = render(<OnboardingScreen />);
  const scan = await waitFor(() => getByTestId("scan-blueprint-btn"));
  fireEvent.press(scan);
  await waitFor(() =>
    expect(getByTestId("notes-input").props.value).toContain("tiled kitchen"));
});
```

---

## M4 — Checklist

### `FE-CHECKLIST-RENDER-01`
Tasks render grouped by room.
```tsx
import { render } from "@testing-library/react-native";
import Dashboard from "../src/screens/Dashboard";
import * as api from "../src/api/client";

test("renders tasks grouped by room", async () => {
  jest.spyOn(api, "getDaily").mockResolvedValue({
    date: "2026-05-25", intensity_cap: 5, tasks: [
      { completion_id: "c1", chore_task_id: "t1", room_name: "Kitchen",
        name: "Wipe counters", estimated_minutes: 5, overdue_days: 0, completed: false },
      { completion_id: "c2", chore_task_id: "t2", room_name: "Bedroom",
        name: "Vacuum", estimated_minutes: 10, overdue_days: 1, completed: false },
    ]});
  const { findByText } = render(<Dashboard />);
  expect(await findByText("Kitchen")).toBeTruthy();
  expect(await findByText("Wipe counters")).toBeTruthy();
  expect(await findByText("Bedroom")).toBeTruthy();
});
```

### `FE-CHECKLIST-TOGGLE-01`
Tapping a task flips its state and calls complete.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import Dashboard from "../src/screens/Dashboard";
import * as api from "../src/api/client";

test("toggling a task calls complete and updates UI", async () => {
  jest.spyOn(api, "getDaily").mockResolvedValue({
    date: "2026-05-25", intensity_cap: 5, tasks: [
      { completion_id: "c1", chore_task_id: "t1", room_name: "Kitchen",
        name: "Wipe counters", estimated_minutes: 5, overdue_days: 0, completed: false }]});
  const complete = jest.spyOn(api, "completeTask").mockResolvedValue({
    completion_id: "c1", chore_task_id: "t1", room_name: "Kitchen",
    name: "Wipe counters", estimated_minutes: 5, overdue_days: 0, completed: true });
  const { findByTestId } = render(<Dashboard />);
  const box = await findByTestId("task-checkbox-c1");
  fireEvent.press(box);
  await waitFor(() => expect(complete).toHaveBeenCalledWith({
    completion_id: "c1", completed: true }));
  await waitFor(() =>
    expect(box.props.accessibilityState.checked).toBe(true));
});
```

### `FE-CHECKLIST-DATE-NAV-01`
The date ribbon re-fetches for the selected date.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import Dashboard from "../src/screens/Dashboard";
import * as api from "../src/api/client";

test("selecting a date refetches for that date", async () => {
  const spy = jest.spyOn(api, "getDaily").mockResolvedValue({
    date: "2026-05-24", intensity_cap: 5, tasks: [] });
  const { getByTestId } = render(<Dashboard />);
  await waitFor(() => expect(spy).toHaveBeenCalled());
  fireEvent.press(getByTestId("date-chip-yesterday"));
  await waitFor(() =>
    expect(spy).toHaveBeenLastCalledWith(expect.stringMatching(/2026-05-24/)));
});
```

---

## M5 — Push token & settings

### `FE-PUSH-TOKEN-CAPTURE-01`
On first dashboard load, a valid token is captured and registered.
```tsx
import { render, waitFor } from "@testing-library/react-native";
import Dashboard from "../src/screens/Dashboard";
import * as api from "../src/api/client";

test("captures and registers the expo push token", async () => {
  jest.spyOn(api, "getDaily").mockResolvedValue({ date: "2026-05-25", intensity_cap: 5, tasks: [] });
  const reg = jest.spyOn(api, "registerPushToken").mockResolvedValue({});
  render(<Dashboard />);
  await waitFor(() =>
    expect(reg).toHaveBeenCalledWith({ expo_push_token: "ExponentPushToken[xyz]" }));
});
```

### `FE-SETTINGS-SCREEN-01`
Settings screen loads values and persists edits.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import SettingsScreen from "../src/screens/SettingsScreen";
import * as api from "../src/api/client";

test("editing intensity persists via PUT", async () => {
  jest.spyOn(api, "getSettings").mockResolvedValue({
    morning_briefing_enabled: true, morning_time: "08:00",
    evening_nudge_enabled: true, evening_time: "19:00",
    daily_intensity_cap: 5, expo_push_token: null });
  const put = jest.spyOn(api, "putSettings").mockResolvedValue({} as any);
  const { findByTestId } = render(<SettingsScreen />);
  const stepper = await findByTestId("intensity-decrement");
  fireEvent.press(stepper);
  await waitFor(() =>
    expect(put).toHaveBeenCalledWith(expect.objectContaining({ daily_intensity_cap: 4 })));
});
```

---

## M6 — Frontend end to end

### `FE-E2E-ONBOARD-TO-TOGGLE-01`
Full app flow with a mocked API client: onboard → land on dashboard → toggle a task.
```tsx
import { render, fireEvent, waitFor } from "@testing-library/react-native";
import App from "../App";
import * as api from "../src/api/client";

test("onboarding through to completing a task", async () => {
  // No home yet -> onboarding shown
  jest.spyOn(api, "listHomes").mockResolvedValueOnce([]);
  jest.spyOn(api, "onboardHome").mockResolvedValue({
    home_id: "h1", name: "Apartment", confidence_score: 0.8,
    rooms: [{ room_id: "r1", name: "Kitchen", floor_type: "Tile",
              chores: [{ chore_task_id: "t1", name: "Wipe counters",
                         frequency_days: 1, estimated_minutes: 5 }] }] });
  jest.spyOn(api, "getDaily").mockResolvedValue({
    date: "2026-05-25", intensity_cap: 5, tasks: [
      { completion_id: "c1", chore_task_id: "t1", room_name: "Kitchen",
        name: "Wipe counters", estimated_minutes: 5, overdue_days: 0, completed: false }]});
  const complete = jest.spyOn(api, "completeTask").mockResolvedValue({
    completion_id: "c1", chore_task_id: "t1", room_name: "Kitchen",
    name: "Wipe counters", estimated_minutes: 5, overdue_days: 0, completed: true });

  const { getByTestId, getByPlaceholderText, findByTestId } = render(<App />);

  // fill onboarding
  fireEvent.press(await findByTestId("add-room-btn"));
  fireEvent.changeText(getByPlaceholderText("Room name"), "Kitchen");
  fireEvent.changeText(getByPlaceholderText("Floor type"), "Tile");
  fireEvent.press(getByTestId("generate-btn"));

  // dashboard appears, toggle the task
  const box = await findByTestId("task-checkbox-c1");
  fireEvent.press(box);
  await waitFor(() => expect(complete).toHaveBeenCalledWith({
    completion_id: "c1", completed: true }));
});
```
