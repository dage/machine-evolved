#include "BulletWorker.h"

BulletWorker::BulletWorker()
	: BulletWorkerBase()
{
	thread = FRunnableThread::Create(this, TEXT("BulletWorker"), 0, TPri_Lowest); // 0 = windows default = 8mb for thread, could specify more
}

BulletWorker::~BulletWorker()
{
	Stop();
}

bool BulletWorker::Init() {
	return true;
}

void BulletWorker::Stop() {
	if (thread) {
		delete thread;
		thread = NULL;
	}
}

// Runs the simulation infintitly
uint32 BulletWorker::Run() {
	UE_LOG(LogTemp, Warning, TEXT("Starting BulletWorker!"));

	double startTime = FPlatformTime::Seconds();
	int numCompleted = runBlocking();
	double deltaTime = FPlatformTime::Seconds() - startTime;

	UE_LOG(LogTemp, Warning, TEXT("Rate: %f creatures/second for worker %d."), numCompleted/deltaTime, id);

	//communicator->shutDown();

	return 0;
}
