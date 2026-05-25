import { render } from "@testing-library/react-native";
import App from "../App";

test("app renders without crashing", () => {
  const { toJSON } = render(<App />);
  expect(toJSON()).toBeTruthy();
});
