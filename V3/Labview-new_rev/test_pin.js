const { AvoidLib } = require('libavoid-js');

async function main() {
    await AvoidLib.load();
    const Avoid = AvoidLib.getInstance();

    const router = new Avoid.Router(Avoid.RouterFlag.OrthogonalRouting.value);

    // Obstacle
    let r = new Avoid.Rectangle(new Avoid.Point(100, 100), new Avoid.Point(200, 200)); 
    let shapeRef = new Avoid.ShapeRef(router, r);

    // Create a ShapeConnectionPin
    // Constructor: ShapeConnectionPin(shapeRef, classId, xOffset, yOffset, isProportional, offset, dir)
    // classId = 1 (Left pin)
    // xOffset = 0, yOffset = 0.5 (proportional, so middle of left edge)
    // isProportional = true
    // offset = 0
    // dir = 4 (Left)
    new Avoid.ShapeConnectionPin(shapeRef, 1, 0, 0.5, true, 0, 4);

    // classId = 2 (Right pin)
    // xOffset = 1.0, yOffset = 0.5
    // dir = 8 (Right)
    new Avoid.ShapeConnectionPin(shapeRef, 2, 1.0, 0.5, true, 0, 8);

    // Now connect to these pins by referencing the shape and classId
    let end1 = new Avoid.ConnEnd(shapeRef, 1);
    
    // Another shape to connect to
    let r2 = new Avoid.Rectangle(new Avoid.Point(300, 100), new Avoid.Point(400, 200));
    let shapeRef2 = new Avoid.ShapeRef(router, r2);
    new Avoid.ShapeConnectionPin(shapeRef2, 1, 0, 0.5, true, 0, 4); // Left pin on shape2
    let end2 = new Avoid.ConnEnd(shapeRef2, 1);

    let connRef = new Avoid.ConnRef(router, end1, end2);

    router.processTransaction();

    let route = connRef.displayRoute();
    let ps = route.ps;
    
    let path = [];
    for (let i = 0; i < ps.size(); i++) {
        let p = ps.get(i);
        path.push({x: p.x, y: p.y});
    }

    console.log("ROUTE:", JSON.stringify(path));
}

main().catch(console.error);
