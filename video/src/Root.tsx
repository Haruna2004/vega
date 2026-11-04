import { Composition } from "remotion";
import { Mend, totalFrames, FPS } from "./Mend";
export const Root = () => <Composition id="Mend" component={Mend} durationInFrames={totalFrames()} fps={FPS} width={1920} height={1080} />;
