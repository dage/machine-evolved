#pragma once

#include "CoreMinimal.h"
#include "Engine/LevelScriptActor.h"
#include "Runnable.h"
#include "RunnableThread.h"
#include "GenericPlatform/GenericPlatformProcess.h"

#include "BulletWorkerBase.h"
#include "BulletInterface.h"
#include "CreatureBase.h"
#include "WorkEvaluator.h"
#include "Communicator.h"

#include <vector>
#include <list>
#include <string>

/**
 * Runs the physics simulation in a seperate thread using UE4s threading system.
 *
 * Based on http://orfeasel.com/implementing-multithreading-in-ue4/
 * See also https://wiki.unrealengine.com/Using_AsyncTasks
 */
class MACHINEWORKER_API BulletWorker : public BulletWorkerBase, public FRunnable
{
public:
	BulletWorker();
	~BulletWorker();
	
	// Begin FRunnable interface....
	virtual bool Init();
	virtual uint32 Run();
	virtual void Stop();
	// ..end FRunnable interface

private:
	FRunnableThread* thread;
};
