#include "CreatureController.h"

void ACreatureController::BeginPlay()
{
	UE_LOG(LogTemp, Log, TEXT("----------------------------> CreatureController::BeginPlay() called."));

	//communicator = AsyncCommunicator::start();

	bullet = BulletInterface();
	bullet.init();

	Super::BeginPlay();

	SetMenuWidget(StartingWidgetClass);
}

void ACreatureController::setNumWorkers(int num) {
	while (workers.size() != num) {
		if (workers.size() < num) {
			// add
			workers.push(new BulletWorker());
		}
		else {
			// remove
			BulletWorker* workerToRemove = workers.top();
			workerToRemove->terminate();
			workers.pop();		// remove element
		}
	}
}


void ACreatureController::onNumThreadsChanged(FString sItem, ESelectInfo::Type seltype) {
	std::string numThreadsString = std::string(TCHAR_TO_UTF8(*sItem));
	int numThreads = std::stoi(numThreadsString);

	setNumWorkers(numThreads);
}


void ACreatureController::onSpawnBestClicked() {
	if (spawnBestWidget == nullptr || spawnBestTextWidget == nullptr)
		return;

	if (!isBestSpawned) {
		spawnBestCreature();
		spawnBestTextWidget->SetText(KILL_SPAWNED_BEST_BUTTON_CAPTION);
	}
	else {
		killBestCreature();
		spawnBestTextWidget->SetText(SPAWN_BEST_BUTTON_CAPTION);
	}

	isBestSpawned = !isBestSpawned;
}

void ACreatureController::onDoRenderChanged(bool isChecked) {
	UGameViewportClient* viewport = GetWorld()->GetGameViewport();

	if(viewport != nullptr)
		viewport->bDisableWorldRendering = !isChecked;
}

void ACreatureController::SetMenuWidget(TSubclassOf<UUserWidget> NewWidgetClass)
{
	if (NewWidgetClass != nullptr) {
		UUserWidget* CurrentWidget = CreateWidget<UUserWidget>(GetWorld(), NewWidgetClass);
		if (CurrentWidget != nullptr) {
			CurrentWidget->AddToViewport();

			serverStatusWidget = (UTextBlock*)CurrentWidget->GetWidgetFromName(FName("ServerStatus"));
			
			spawnBestWidget = (UButton*)CurrentWidget->GetWidgetFromName(FName("SpawnBest"));
			spawnBestWidget->OnClicked.AddDynamic(this, &ACreatureController::onSpawnBestClicked);
			spawnBestTextWidget = (UTextBlock*)CurrentWidget->GetWidgetFromName(FName("SpawnBestText"));
			if(spawnBestTextWidget != nullptr)
				spawnBestTextWidget->SetText(SPAWN_BEST_BUTTON_CAPTION);

			numThreadsWidget = (UComboBoxString*)CurrentWidget->GetWidgetFromName(FName("NumThreads"));
			numThreadsWidget->OnSelectionChanged.AddDynamic(this, &ACreatureController::onNumThreadsChanged);

			doRenderWidget = (UCheckBox*)CurrentWidget->GetWidgetFromName(FName("DoRender"));
			doRenderWidget->OnCheckStateChanged.AddDynamic(this, &ACreatureController::onDoRenderChanged);
		}
	}
}

void ACreatureController::spawnBestCreature() {
	auto jsonObject = communicator->getBestCreature();

	if (!jsonObject.empty()) {
		btVector3 position = btVector3(0, 0, 0);
		previewCreature = new Creature(&bullet, GetWorld(), capsuleMaterial, position, jsonObject.get_child("creature"));

		bestCreatureEvaluator.add(jsonObject.get_child("task"), previewCreature);
	}
}

void ACreatureController::killBestCreature() {
	bestCreatureEvaluator.remove(previewCreature);

	previewCreature->terminate();
	previewCreature = nullptr;
}

void ACreatureController::Tick(float DeltaTime)
{
	bullet.tick(1 / 60.f);		// using constant delta time to make it deterministic

	if (serverStatusWidget != nullptr) {
		double currentTime = FPlatformTime::Seconds();
		if (currentTime - uiUpdateTimeStamp > 1.) {		// don't update ui every tick
			uiUpdateTimeStamp = currentTime;
			std::string serverStatus = communicator->getServerStatus();
			if (serverStatus != "")
				serverStatusWidget->SetText(FText::FromString(FString(UTF8_TO_TCHAR(serverStatus.c_str()))));
		}
	}

	if(previewCreature != nullptr)
		previewCreature->tick();

	std::vector<WorkEvaluator::TASK*> finishedTask = bestCreatureEvaluator.tick();
	if (finishedTask.size() == 1) {
		WorkEvaluator::MOVE_FAR_TASK* task = (WorkEvaluator::MOVE_FAR_TASK*)finishedTask[0];
		UE_LOG(LogTemp, Log, TEXT("Best creature replay finished. maxDistance=%f"), task->maxDistance);
	}

	Super::Tick(DeltaTime);
}


void ACreatureController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	UE_LOG(LogTemp, Log, TEXT("<---------------------------- CreatureController::EndPlay(...) called."));
	
	setNumWorkers(0);

	bullet.destroy();

	Super::EndPlay(EndPlayReason);

	//communicator->shutDown();
}