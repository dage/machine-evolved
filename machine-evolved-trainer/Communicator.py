import socketserver
import json
import sys
import time
from pprint import pprint

# Handles all communication with clients, serving workloads, getting results.
class Communicator():
	def __init__(self, getWorkCallback, getWorkBatchCallback, doStepBatchCallback, registerResultCallback, getServerStatusCallback, getBestCreatureCallback):
		self.HOST = "127.0.0.1"
		self.PORT = 9999
		self.isStopped = False
		
		self.server = socketserver.ThreadingTCPServer((self.HOST, self.PORT), RequestHandler)
		#self.server = socketserver.TCPServer((self.HOST, self.PORT), RequestHandler)
		self.server.callbacks = { "getWork": getWorkCallback, "getWorkBatch": getWorkBatchCallback, "doStepBatch": doStepBatchCallback, "registerResult": registerResultCallback, "getServerStatus" : getServerStatusCallback, "getBestCreature": getBestCreatureCallback }

	def start(self):
		print("Listening on " + self.HOST + ":" + str(self.PORT))
		self.server.serve_forever()

	def stop(self):
		self.isStopped = True
		self.server.shutdown()

class RequestHandler(socketserver.BaseRequestHandler):
	def handle(self):
		def receiveJson():
			BLOCK_SIZE = 4096
			allBlocks = ""
			jsonEnded = False
			block = "dummy-overwritten"
			isFirstBlock = True
			bracketCount = 0
			while not jsonEnded and block:
				block = self.request.recv(BLOCK_SIZE)
				if block:
					block = block.decode("utf-8")
					numLeftBrackets = block.count("{")
					numRightBrackets = block.count("}")
					if isFirstBlock and numLeftBrackets == 0:
						print("Received a packet that was not json. Ignoring....")
						block = ""	# trigger break out of loop, same as socket closed
					bracketCount += numLeftBrackets - numRightBrackets
					if bracketCount == 0:
						jsonEnded = True
					allBlocks += block
					isFirstBlock = False
			
			return allBlocks
		
		# receive request:
		self.data = receiveJson()

		#print("<-- received {} bytes (of {}) from {}: {}".format(len(self.data), str(self.PACKET_SIZE), self.client_address[0], self.data))
		#print("<-- received {} bytes (of {}) from {}".format(len(self.data), str(self.PACKET_SIZE), self.client_address[0]))

		# process:
		data = json.loads(self.data)
		#print("Communicator data type=" + data["type"])

		if data["type"] == "PING":
			data["response"] = "PING"
			response = json.dumps(data);
		elif data["type"] == "GET_WORK":
			response = self.server.callbacks["getWork"]()
		elif data["type"] == "GET_WORK_BATCH":
			response = self.server.callbacks["getWorkBatch"](data["data"])
		elif data["type"] == "STEP_BATCH":
			response = self.server.callbacks["doStepBatch"](data["data"])
		elif data["type"] == "GET_BEST_CREATURE":
			response = self.server.callbacks["getBestCreature"]()
		elif data["type"] == "GET_SERVER_STATUS":
			response = self.server.callbacks["getServerStatus"]()
		elif data["type"] == "RESULT":
			response = self.server.callbacks["registerResult"](data["data"])
		
		#pprint(response)

		# send response:
		#print("--> {}: sent {} bytes (of {}) to {}: {}".format(data["type"], len(response), str(self.PACKET_SIZE), self.client_address[0], response))
		#print("--> {}: sent {} bytes (of {}) to {}".format(data["type"], len(response), str(self.PACKET_SIZE), self.client_address[0]))

		if data["type"] != "RESULT":
			self.request.sendall(response.encode("utf-8"))