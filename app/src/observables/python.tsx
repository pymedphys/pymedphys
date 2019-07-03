import { BehaviorSubject } from 'rxjs';

export interface IPythonData {
    gantryAngle: number
}


export const pythonReady = new BehaviorSubject<boolean>(false);
export const pythonData = new BehaviorSubject<IPythonData>({
    gantryAngle: -120
});
export const pythonCode = new BehaviorSubject<string>("")