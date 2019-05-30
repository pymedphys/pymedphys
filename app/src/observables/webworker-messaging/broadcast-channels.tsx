// import { v4 } from 'uuid';

// const url = new URL(window.location.href);
// let workerString = url.searchParams.get("worker");
// let mainString = url.searchParams.get("main");

// if (workerString === null) {
//     workerString = v4();
// }
// if (mainString === null) {
//     mainString = v4();
// }

const workerChannel = new BroadcastChannel("worker");
const mainChannel = new BroadcastChannel("main");


export { workerChannel, mainChannel }