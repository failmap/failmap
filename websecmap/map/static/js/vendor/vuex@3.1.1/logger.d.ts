/**
 * Types for the logger plugin.
 * This file must be put alongside the JavaScript file of the logger.
 */

import { Payload, Plugin } from "../../../../../../../../../../../../Users/elger/Downloads/vuex-3.1.1/types";

export interface LoggerOption<S> {
  collapsed?: boolean;
  filter?: <P extends Payload>(mutation: P, stateBefore: S, stateAfter: S) => boolean;
  transformer?: (state: S) => any;
  mutationTransformer?: <P extends Payload>(mutation: P) => any;
}

export default function createLogger<S>(option?: LoggerOption<S>): Plugin<S>;
