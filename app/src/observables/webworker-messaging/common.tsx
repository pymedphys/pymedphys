import {
  Subject, Observable, asyncScheduler
} from 'rxjs';
import { filter, observeOn } from 'rxjs/operators';

import { v4 } from 'uuid';

interface IMessage extends Readonly<{}> {
  uuid: string;
  type: string;
  data: {};
  transferables?: Transferable[];
}

interface IData extends Readonly<{}> {

}


interface INullData extends Readonly<{}> {

}

interface INullMessage extends IMessage {
  type: '';
  data: INullData;
}

interface IExecuteRequestData extends IData {
  code: string
}

interface IExecuteRequestMessage extends IMessage {
  type: 'executeRequest';
  data: IExecuteRequestData
}

interface IFileTransferRequestData extends IData {
  filepath: string
}

interface IFileTransferRequestMessage extends IMessage {
  type: 'fileTransferRequest';
  data: IFileTransferRequestData
}

interface IFileTransferMessage extends IMessage {
  type: 'fileTransfer';
  data: IFileTransferData;
}

interface IFileTransferData extends IData {
  file: ArrayBuffer,
  filepath: string
}

interface IFileTransferMessage extends IMessage {
  type: 'fileTransfer';
  data: IFileTransferData;
}

interface ILanguageServerData extends IData {

}

interface ILanguageServerMessage extends IMessage {
  type: 'languageServer';
  data: ILanguageServerData;
}

interface IReplyData extends IData {
  error?: any
  result?: any
}

interface IReplyMessage extends IMessage {
  type: 'reply';
  data: IReplyData;
}

interface IInitialiseData extends IData {

}

interface IInitialiseMessage extends IMessage {
  type: 'initialise';
  data: IInitialiseData;
}
type IPyodideType = '' | 'executeRequest' | 'fileTransfer' | 'languageServer' | 'reply' | 'initialise';
type IPyodideData = INullData | IExecuteRequestData | IFileTransferRequestData | IFileTransferData | ILanguageServerData | IReplyData | IInitialiseData;
export type IPyodideMessage = INullMessage | IExecuteRequestMessage | IFileTransferRequestMessage | IFileTransferMessage | ILanguageServerMessage | IReplyMessage | IInitialiseMessage;

interface IMessengers extends Readonly<{}> {
  next: Function;
  subscribe: Function;
  executeRequest: Observable<IExecuteRequestMessage>;
  fileTransfer: Observable<IFileTransferMessage>;
  fileTransferRequest: Observable<IFileTransferRequestMessage>;
  languageServer: Observable<ILanguageServerMessage>;
  reply: Observable<IReplyMessage>;
  initialise: Observable<IInitialiseMessage>;
}

export function createUuid(): string {
  const uuid = v4() as string
  return uuid
}

const createBaseMessengers = () => {
  let messenger = new Subject<IPyodideMessage>()
  let scheduled = messenger.pipe(observeOn(asyncScheduler))
  // let scheduled = messenger

  const messengers: IMessengers = {
    next: (value: IPyodideMessage) => messenger.next(value),
    subscribe: (func: (value: IPyodideMessage) => void) => { scheduled.subscribe(func) },
    executeRequest: scheduled.pipe(filter((data: IPyodideMessage) => data.type === 'executeRequest')) as Observable<IExecuteRequestMessage>,
    fileTransfer: scheduled.pipe(filter(data => data.type === 'fileTransfer')) as Observable<IFileTransferMessage>,
    fileTransferRequest: scheduled.pipe(filter(data => data.type === 'fileTransferRequest')) as Observable<IFileTransferRequestMessage>,
    languageServer: scheduled.pipe(filter(data => data.type === 'languageServer')) as Observable<ILanguageServerMessage>,
    reply: scheduled.pipe(filter(data => data.type === 'reply')) as Observable<IReplyMessage>,
    initialise: scheduled.pipe(filter(data => data.type === 'initialise')) as Observable<IInitialiseMessage>
  }

  return messengers
}

const createMessengers = () => {
  const receiver = createBaseMessengers()
  const sender = createBaseMessengers()

  const sendMessage = (data: IPyodideData, type: any) => {
    const uuid = createUuid();
    const responses = receiver.reply.pipe(filter(message => message.uuid === uuid))

    const message: IPyodideMessage = {
      uuid: uuid,
      type: type,
      data: data
    }

    sender.next(message)
    return responses
  }

  const sendExecuteRequest = (code: string): Observable<IReplyMessage> => {
    const data: IExecuteRequestData = { code }
    return sendMessage(data, 'executeRequest')
  }

  const sendLanguageServer = (data: ILanguageServerMessage): Observable<IReplyMessage> => {
    return sendMessage(data, 'languageServer')
  }

  const sendInitialise = (): Observable<IReplyMessage> => {
    return sendMessage({}, 'initialise')
  }

  const sendReply = (uuid: string, data: IReplyData) => {
    const message: IReplyMessage = {
      uuid: uuid,
      type: 'reply',
      data: data
    }

    sender.next(message)
  }

  const sendFileTransferRequest = (filepath: string): Observable<IFileTransferMessage> => {
    const uuid = createUuid();
    const responses = receiver.fileTransfer.pipe(filter(message => message.uuid === uuid))

    const message: IPyodideMessage = {
      uuid: uuid,
      type: 'fileTransferRequest',
      data: { filepath }
    }

    sender.next(message)
    return responses
  }

  const sendFileTransfer = (file: ArrayBuffer, filepath: string, uuid?: string): Observable<IReplyMessage> => {
    if (uuid === undefined) {
      uuid = createUuid();
    }
    const responses = receiver.reply.pipe(filter(message => message.uuid === uuid))
    const message: IFileTransferMessage = {
      uuid: uuid,
      type: 'fileTransfer',
      data: { file, filepath },
    }

    message.transferables = [message.data.file]

    sender.next(message)
    return responses
  }

  const messengers = {
    sender, receiver, sendExecuteRequest, sendLanguageServer, sendInitialise,
    sendFileTransferRequest, sendFileTransfer, sendReply
  }

  return messengers
}

const workerMessengers = createMessengers()
const mainMessengers = createMessengers()

export {
  workerMessengers, mainMessengers
}