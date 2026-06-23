const fs = require('fs');
const { AvoidLib } = require('libavoid-js');

async function main() {
    if (process.argv.length < 4) {
        console.error("Usage: node avoid_router.js <input.json> <output.json>");
        process.exit(1);
    }

    const inputFile = process.argv[2];
    const outputFile = process.argv[3];

    const data = JSON.parse(fs.readFileSync(inputFile, 'utf-8'));

    await AvoidLib.load();
    const Avoid = AvoidLib.getInstance();

    const router = new Avoid.Router(Avoid.RouterFlag.OrthogonalRouting.value);
    
    // Set parameters
    router.setRoutingParameter(Avoid.RoutingParameter.idealNudgingDistance.value, 10.0);
    router.setRoutingParameter(Avoid.RoutingParameter.shapeBufferDistance.value, 10.0);

    const shapes = {}; // Map of shapeId to ShapeRef
    const pinsMap = {}; // Map of shapeId_pinId to classId integer

    let nextClassId = 1;

    // Process obstacles
    for (const obs of data.obstacles) {
        let r = new Avoid.Rectangle(
            new Avoid.Point(obs.x, obs.y), 
            new Avoid.Point(obs.x + obs.w, obs.y + obs.h)
        );
        let shapeRef = new Avoid.ShapeRef(router, r);
        shapes[obs.id] = shapeRef;

        if (obs.pins) {
            for (const pin of obs.pins) {
                const classId = nextClassId++;
                // ShapeConnectionPin(shapeRef, classId, xOffset, yOffset, isProportional, offset, dir)
                new Avoid.ShapeConnectionPin(
                    shapeRef, classId, 
                    pin.xOff, pin.yOff, 
                    true, 0, pin.dir
                );
                pinsMap[`${obs.id}_${pin.id}`] = classId;
            }
        }
    }

    const conns = {}; // Map of pipeId to ConnRef

    // Process connections
    for (const conn of data.connections) {
        let startClassId = pinsMap[`${conn.start.shape}_${conn.start.pin}`];
        let endClassId = pinsMap[`${conn.end.shape}_${conn.end.pin}`];

        if (startClassId && endClassId) {
            let end1 = new Avoid.ConnEnd(shapes[conn.start.shape], startClassId);
            let end2 = new Avoid.ConnEnd(shapes[conn.end.shape], endClassId);
            let connRef = new Avoid.ConnRef(router, end1, end2);
            conns[conn.id] = connRef;
        } else {
            if (!startClassId) console.error(`Missing start pin: ${conn.start.shape}_${conn.start.pin}`);
            if (!endClassId) console.error(`Missing end pin: ${conn.end.shape}_${conn.end.pin}`);
            console.error(`Missing pin definition for connection ${conn.id}`);
        }
    }

    router.processTransaction();

    const result = {};

    for (const pipeId in conns) {
        let route = conns[pipeId].displayRoute();
        let ps = route.ps;
        let path = [];
        for (let i = 0; i < ps.size(); i++) {
            let p = ps.get(i);
            path.push([p.x, p.y]);
        }
        result[pipeId] = path;
    }

    fs.writeFileSync(outputFile, JSON.stringify(result, null, 2));
    console.log("Routing complete.");
}

main().catch(err => {
    console.error(err);
    fs.writeFileSync('avoid_router_error.log', err.stack || err.toString());
    process.exit(1);
});

