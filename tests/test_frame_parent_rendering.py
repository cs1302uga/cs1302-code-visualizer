"""Native checks for optional environment-frame parent connectors."""

import json
from pathlib import Path

from cs1302_code_visualizer import browser_driver


def test_parent_frames_keep_left_attachments_and_export_detours(rendering_session):
    """Nested parents keep their anchors when a clear curve becomes obstructed."""
    fixture = (
        Path(__file__).resolve().parents[1]
        / "cs1302_code_visualizer/frontend/tests/fixtures/map-keys.json"
    )
    trace = json.loads(fixture.read_text())
    step = trace["trace"][0]
    step["heap"] = {}
    step["heap_attrs"] = {}
    original = step["stack_to_render"][0]
    step["stack_to_render"] = []
    for index in range(3):
        frame = dict(original)
        frame.update(
            frame_id=index,
            unique_hash=str(index),
            func_name=f"frame{index}",
            parent_frame_id_list=[index - 1] if index else [],
            encoded_locals={"value": index},
            ordered_varnames=["value"],
            locals_attrs={"value": {"type": "int", "final": False}},
        )
        step["stack_to_render"].append(frame)
    trace["trace"] = [step]
    with browser_driver.online_python_tutor_frontend(
        json.dumps(trace),
        text_memory_labels=False,
        session=rendering_session,
    ) as frontend:
        driver = frontend["driver"]
        # Exercise the existing ExecutionVisualizer option, including its normal
        # parent-connector creation path, rather than connecting frames by hand.
        viz = driver.execute_script(
            """
            const old=window.optFrontend, Constructor=old.constructor;
            const root=document.createElement('div');root.id='parent-regression';
            root.style.cssText=old.domRoot[0].style.cssText;
            document.body.append(root);old.domRoot[0].remove();
            window.optFrontend=new Constructor(root.id,arguments[0],
                {...old.params,drawParentPointers:true});
            return root.querySelector('#dataViz');
        """,
            trace,
        )
        result = driver.execute_script("""
            const v=window.optFrontend,m=v.dataViz.jsPlumbInstance;
            v.redrawConnectors();
            const parents=m.connections.filter(c=>c.scope==='frameParentPointer');
            const initial=parents.map(c=>c.pathElement.getAttribute('d'));
            const middle=parents[0].pathElement.getPointAtLength(parents[0].pathElement.getTotalLength()/2);
            const dataViz=v.dataViz.domRoot[0].querySelector('#dataViz');
            dataViz.style.position='relative';
            const dataRect=dataViz.getBoundingClientRect(),canvasRect=m.container.getBoundingClientRect();
            const label=document.createElement('span');label.textContent='obstacle';
            label.style.cssText=`position:absolute;left:${canvasRect.left+middle.x-dataRect.left-15}px;top:${canvasRect.top+middle.y-dataRect.top-6}px;font-size:10px;white-space:nowrap`;
            dataViz.append(label);
            m.repaintEverything();
            const after=parents.map(c=>c.pathElement.getAttribute('d'));
            const origin=m.container.getBoundingClientRect(), texts=[],range=document.createRange();
            const walker=document.createTreeWalker(v.dataViz.domRoot[0],NodeFilter.SHOW_TEXT);
            while(walker.nextNode()){
                const n=walker.currentNode;
                if(!n.textContent.trim()||n.parentElement.closest('svg,script,style'))continue;
                range.selectNodeContents(n);texts.push(...range.getClientRects());
            }
            const errors=[];
            for(const c of parents){
                const s=c.source[0].getBoundingClientRect(),t=c.target[0].getBoundingClientRect();
                const points=c.arrowElement.getAttribute('points').split(' ').map(p=>p.split(',').map(Number));
                if(Math.abs(Number(c.dotElement.getAttribute('cx'))+origin.left-s.left)>.1)errors.push('source side');
                if(Math.abs(points[0][0]+origin.left-t.left)>.1)errors.push('target side');
                const dot=c.dotElement.getBoundingClientRect(),head=c.arrowElement.getBoundingClientRect();
                if(texts.some(r=>r.width&&r.height&&[dot,head].some(b=>
                    b.right>r.left-1&&b.left<r.right+1&&b.bottom>r.top-1&&b.top<r.bottom+1)))errors.push('endpoint text');
                const p=c.pathElement;
                for(let d=1;d<p.getTotalLength();d+=.5){
                    const q=p.getPointAtLength(d),x=q.x+origin.left,y=q.y+origin.top;
                    if(texts.some(r=>r.width&&r.height&&x>r.left-1.5&&x<r.right+1.5&&y>r.top-1.5&&y<r.bottom+1.5))errors.push('text');
                    if([s,t].some(r=>x>r.left&&x<r.right&&y>r.top&&y<r.bottom))errors.push('frame interior');
                }
            }
            m.repaintEverything();
            return {count:parents.length,errors:[...new Set(errors)],changed:initial[0]!==after[0],
                stable:JSON.stringify(after)===JSON.stringify(parents.map(c=>c.pathElement.getAttribute('d')))};
        """)
        assert result == {"count": 2, "errors": [], "changed": True, "stable": True}
        bounds = browser_driver._export_bounds(driver, viz)
        paint = driver.execute_script("""
            return [...window.optFrontend.dataViz.jsPlumbInstance.connections].map(c=>
                c.groupElement.getBoundingClientRect().toJSON());
        """)
        for rect in paint:
            assert rect["left"] >= 0 and rect["top"] >= 0
            assert rect["left"] >= bounds["left"] and rect["right"] <= bounds["right"]
            assert rect["top"] >= bounds["top"] and rect["bottom"] <= bounds["bottom"]
        for image_format in ["SVG", "PNG"]:
            image = browser_driver._capture_viz(
                driver,
                viz,
                format=image_format,
                dpi=1,
                visualizer="pytutor",
                session=rendering_session,
            )
            assert b"<svg" in image if image_format == "SVG" else image.startswith(b"\x89PNG")
