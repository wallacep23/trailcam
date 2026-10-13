import { Placeholder } from "../../components/Placeholder";
import { getScreen } from "../../lib/screens";

const screen = getScreen("forecast");

/** Forecast screen (DESIGN §14). Placeholder until Forecast is built. */
export function ForecastPage() {
  return <Placeholder screen={screen} />;
}
