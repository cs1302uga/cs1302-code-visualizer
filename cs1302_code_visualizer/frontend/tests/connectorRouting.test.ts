import { describe, expect, it } from "vitest";
import { ConnectorRouting, type MeasuredConnectorEdge, type MeasuredConnectorScene } from "../js/connectorRouting";
import type { Rect } from "../js/referenceRouting";

function freeze<T>(value:T):T {
  if(value&&typeof value==="object") {
    Object.freeze(value);
    Object.values(value).forEach(freeze);
  }
  return value;
}

describe("pure controlled connector planning",()=>{
  it.each(["independent","shared"] as const)(
    "reports the original scene edge after %s target ordering without mutating the measurement",policy=>{
      const frame:Rect={left:20,top:10,right:65,bottom:80};
      const far:Rect={left:150,top:20,right:200,bottom:80};
      const near:Rect={left:70,top:20,right:120,bottom:80};
      const blocker:Rect={left:55,top:48,right:65,bottom:52};
      const canvas:Rect={left:0,top:0,right:220,bottom:120};
      const input:MeasuredConnectorScene={objects:[frame,far,near,blocker],heapOwners:[false,true,true,true],
        text:[blocker],textOwners:[3],localEndpoints:[],content:canvas,canvas,
        // Canonical source order visits the far target first; crowded controlled
        // routing visits the near target first, whose source is covered.
        edges:[far,near].map((target,i):MeasuredConnectorEdge=>({connectionIndex:10+i,sourceId:`source-${i}`,targetId:`target-${i}`,
          heapOrigin:false,targetIdentity:i,styleKey:"same-style",sharingEligible:true,
          attachment:{source:[60,30+i*20],sourceBox:{left:40,top:20+i*20,right:64,bottom:40+i*20},
            enclosure:frame,target,targetKey:`target-${i}`,sourceOwner:0,targetOwner:1+i,returning:false,width:1}}))};
      const before=JSON.stringify(input);
      freeze(input);
      expect(new ConnectorRouting().plan(input,false,policy)).toMatchObject({ok:false,
        constraint:{kind:"covered-source",edgeIndex:1,blockerOwners:[3]}});
      expect(JSON.stringify(input)).toBe(before);
    });
});
