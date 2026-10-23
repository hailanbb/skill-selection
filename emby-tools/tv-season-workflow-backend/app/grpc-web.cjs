// Binary gRPC-Web transport for HTTP reverse proxies; no browser or DOM dependency.
async function grpcWeb(origin,token,definition,request){
 const payload=definition.requestSerialize(request),head=Buffer.alloc(5);head.writeUInt32BE(payload.length,1);
 let response;try{response=await fetch(new URL(definition.path,origin),{method:'POST',redirect:'error',headers:{'content-type':'application/grpc-web+proto','x-grpc-web':'1','authorization':'Bearer '+token},body:Buffer.concat([head,payload]),signal:AbortSignal.timeout(60000)});}catch{throw Error('CloudDrive gRPC-Web request failed or timed out');}
 if(!response.ok)throw Error('CloudDrive gRPC-Web HTTP '+response.status);
 const bytes=Buffer.from(await response.arrayBuffer()),messages=[];let offset=0,status=response.headers.get('grpc-status');
 while(offset<bytes.length){if(offset+5>bytes.length)throw Error('Truncated gRPC-Web frame');const flags=bytes[offset],size=bytes.readUInt32BE(offset+1);offset+=5;if(offset+size>bytes.length)throw Error('Truncated gRPC-Web message');const data=bytes.subarray(offset,offset+size);offset+=size;if(flags===128){const trailers=data.toString('utf8');status=/(?:^|\r?\n)grpc-status:\s*(\d+)/i.exec(trailers)?.[1]??status;}else if(flags===0)messages.push(definition.responseDeserialize(data));else throw Error('Unsupported compressed gRPC-Web frame');}
 if(status!=='0')throw Error('CloudDrive gRPC-Web status '+(status??'missing'));
 return messages;
}
module.exports=grpcWeb;
